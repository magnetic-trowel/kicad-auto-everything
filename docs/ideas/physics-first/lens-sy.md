# Physics-first ideas: lens SY (symmetry, reciprocity and duality)

The argument, principles P1–P7 and numbers are in [lens-sy](../../topics/physics/lens-sy.md). Everything here is a proposal [I] unless a number is tagged [C], computed by [sy_duality_balance.py](../../../tools/research/physics/sy_duality_balance.py) or [sy_images_symmetry.py](../../../tools/research/physics/sy_images_symmetry.py).

Tags:
- **new**: not in the [catalog](README.md).
- **combo**: a new combination of existing ideas.
- **sharp**: an existing idea made exact or buildable.

Effort: S (days), M (weeks), L (months). Principles:
- **P1** reciprocity and the lead field; **P1′** adjoint ≠ reciprocity;
- **P2** duality (a: EM and Babinet; b: sheets, φ/R_s ↔ ψ; c: networks);
- **P3** images;
- **P4** mirror decomposition and Curie;
- **P5** gauge;
- **P6** scale;
- **P7** Noether-style invariants.

## Try first

| Rank | Idea | Why |
|---|---|---|
| 1 | SY7 + SY9 cut price for any objective | Two existing solves; fixes the optimizer's 13–35× blind spot on cuts [C] |
| 2 | SY10 + SY11 node budgets and buried victims | Planes do not quiet dv/dt nodes (C_m ∝ h^0.19 [C]); changes stackup and routing advice |
| 3 | SY15 + SY14 imbalance-step ledger in one balance currency | Replaces "accumulate asymmetry" with the physics that converts modes |
| 4 | SY2 periodic adjoint | The missing susceptibility engine for converters and sampled ADCs |
| 5 | SY18 feed symmetry group | A seconds-long graph check that guarantees current sharing |

**Shared with lens CT.** Four ideas also appear in [lens CT](lens-ct.md), derived there from conservation and here from symmetry and duality. Treat each pair as one idea with two derivations:
- SY6 ≈ CT1 (the exact cut law);
- SY9 ≈ CT2 (crack-augmented adjoint);
- SY16 ≈ CT10 (antiphase node pairing);
- the voltage-driven half of SY27 ≈ CT9 (board–world charge).

SY7 (cross-objective price) and SY8 (bridge dual) appear only here.

---

## A. Reciprocity and adjoints

**SY1. Two primitives: `adjoint(J)` and `lead_field(port)`** — *sharp, S.*
- **Mechanism:** the solver API separates two operations.
  - The circuit adjoint is a transposed solve of the linearized circuit, which may be non-reciprocal (SPICE `.noise` or our MNA).
  - The field lead field is a forward field solve with unit current fed into the victim port. That is valid because the interconnect is reciprocal.
  - Every coupling query is ∫source·lead field, and every output sensitivity is adjoint × lead field.
- **Principle:** P1, P1′.
- **Why:** keeping them apart shows which shortcut fails where: active parts break reciprocity but not adjoints, and nonlinear victims break both.
- **Test:** compute 20 couplings on a buck + ADC board by per-aggressor solves and by lead fields; they must agree to solver tolerance. Check `.noise` against a transposed MNA with a non-reciprocal op-amp model.

**SY2. Periodic adjoint for switching and sampled victims** — *new, M.*
- **Mechanism:**
  - Linearize converters (FB comparator, PWM), sampled ADC inputs, choppers and PLL phase detectors around their periodic steady state with harmonic balance.
  - Solve the transposed harmonic-transfer system once per output frequency. That gives every injection site's susceptibility at every sideband f ± k·f_s, which is what SpectreRF's PXF does (Telichevesky, Kundert, White 1996 [S]).
- **Principle:** P1′, P7 (time translation broken to f mod f_s).
- **Why:** LTI `.noise` at a DC point cannot see aliasing or frequency translation, which is how switching harmonics reach a sampled ADC's passband. DR36 plans frequencies but has no transfer function to plan with.
- **Test:** on a buck FB node and a SAR ADC model, compare the prediction with transient tone injection at 30 frequencies (±1 dB).

**SY3. Power budgets for rectifying victims** — *new, S.*
- **Mechanism:**
  - Flag op-amp, PGA and comparator inputs whose datasheet gives EMIRR or whose model rectifies.
  - Budget coupled RF power there, not voltage: offset ∝ V_rf², scaled from the EMIRR test amplitude.
  - Allocate with the square-power form of DR9's rule.
- **Principle:** the linear path is P1; the terminal is nonlinear.
- **Why:** linear budgets assume 6 dB less coupling gives 6 dB less error. For a rectifying victim it gives 12 dB, so effort there pays twice and linear allocation misplaces it.
- **Test:** SPICE with an EMIRR-calibrated input model, plus bench tone injection. The slope of offset against amplitude should be 2.

**SY4. Reciprocity residual as a free solver audit** — *sharp, S.*
- **Mechanism:** every extracted multiport must satisfy Z = Zᵀ. This covers PEEC R and Lp, capacitance matrices, κ_ab maps, crosstalk tables and macromodels.
  - Report ‖Z − Zᵀ‖/‖Z‖ on every call.
  - Reject passive macromodels (SIM33) whose fit breaks it.
- **Principle:** P1.
- **Why:** an asymmetric mutual always means a meshing, port or assembly bug. The check is free and catches errors before they become rewards.
- **Test:** run on all existing solvers (SIM46) and on deliberately mis-meshed cases; count bugs found.

**SY5. Emission and immunity from one solve** — *combo, S.*
- **Mechanism:**
  - For each structure and connector pair, the κ_ab or lead-field solve gives the emission coupling.
  - By reciprocity it also gives the coupling of a cable common-mode disturbance (BCI or radiated) into the structure.
  - Allocate one budget against the tighter of the emission limit and the immunity level × victim threshold. Only the victim's nonlinear response needs new modelling.
- **Principle:** P1.
- **Why:** [research-gaps](../../topics/physics/research-gaps.md) lists immunity as thin, but its linear half is already computed for emission.
- **Test:** on 3 boards with emission and BCI data, check that predicted immunity weak spots match emission hot spots and BCI failures.

## B. Duality: cuts and bridges

**SY6. Image-exact slit cost** — *sharp, S.*
- **Mechanism:** replace (π/4)R_s(Δψ/I)² with ΔR = −(2/π)R_s·ln cos(πΔψ/2I) for interior cuts, and twice that for edge notches. This comes from images in the strip edges.
- **Principle:** P3, P2b.
- **Why:** the quadratic law reads 28% low at Δψ/I = 0.75 and cannot see that a severing cut costs infinity. The image form matches zero-width-cut FD within 0.7–1.5% [C].
- **Test:** 100 random cuts on real pours with non-uniform flow; log-cos with the local Δψ against FD.

**SY7. Cut price for any objective: Δψ_u·Δψ_λ** — *new, S.*
- **Mechanism:**
  - For any objective J (drop at one load, voltage across a sense pair, loss in a region), run one forward and one adjoint solve.
  - A cut then costs ΔJ ≈ (π/4)R_s·Δψ_u·Δψ_λ, where Δψ is the current crossing the cut line in each solution.
  - The sign says whether the cut helps or hurts this J.
- **Principle:** P1 plus P2b (the crack's polarization tensor).
- **Why:** Δψ² prices total loss only, and a cut that is harmless for loss can wreck one load's drop or a Kelvin reading. For a Kelvin-pair objective this form is within 3–12% of FD, where the plain adjoint was 13–35× low [C].
- **Test:** 100 cuts × 3 objectives on 5 boards against re-solves.

**SY8. Bridge price by Δφ, the dual of the slit law** — *new, S.*
- **Mechanism:**
  - Price straps, inlays, extra vias to a parallel layer and stitched parallel traces by the saving ΔR ≈ (π/4)R_s·(Δφ/(R_s·I))², for a thin, highly conducting element laid along the flow.
  - For a lumped strap of conductance G across Δφ, ΔP ≈ −G·Δφ² while G is small.
  - Place bridges along streamlines where Δφ is largest. That is also where cuts are free.
- **Principle:** P2b (Keller).
- **Why:** designers bridge "where it looks thin". FD agrees within 0.2% at Δφ/(R_s·I) = 0.25 [C].
- **Test:** 50 candidate straps on 5 high-current boards; predicted against FD ΔR ranking.

**SY9. Polarization tensors for slender defects** — *sharp, S.*
- **Mechanism:** in OP41 and SIM24, give thin voids, antipad rows, slits and thin straps their anisotropic polarization tensors:
  - a crack is π(ℓ/2)² normal to the cut and 0 along it;
  - a needle is the dual.
  
  This replaces "removed area × energy density".
- **Principle:** P2b, P3.
- **Why:** the area-based adjoint underestimates cuts 13–35× [C]. With the tensor it is accurate to about 10%, so one adjoint prices every small edit; finite edits need exact Woodbury updates.
- **Test:** SIM25's 100-slot set, error before and after.

## C. Nodes and loops once the plane breaks duality

**SY10. Node budgets in ∫V dA with h-free coupling kernels** — *new, S.*
- **Mechanism:**
  - Describe each dv/dt node by its voltage-area moment p = 2ε0∫V dA over its reference.
  - Couple it to victims with ε0·A_a·A_v/(2πr³) in 3-D, or ε0·w_a·w_v/(πD²) per unit length in 2-D.
  - Do not use εA/h × K(D/h).
- **Principle:** P2 broken by P3. A PEC images charges into dipoles and flat loops into quadrupoles.
- **Why:** FD gives C_m ∝ h^0.19 for wide strips while L_m ∝ h^1.98 [C]. The K-factor model credits thin prepreg with capacitive isolation it does not give low-impedance victims.
- **Test:** 2-D and 3-D solves of SW pads near FB and XIN at h = 0.075–0.2 mm against both models; E-probe scans on a buck coupon.

**SY11. Bury the victim, not the aggressor** — *new, S.*
- **Mechanism:**
  - Where a high-impedance victim (FB, XIN, ADC input, reference) must pass within a few mm of dv/dt copper, route it on an inner layer under the plane, or under a top shield.
  - Drop coplanar guards over thin dielectric.
- **Principle:** P3. An electric shield must sit in the field's path, and here that path runs through the air above the board.
- **Why:** a grounded coplanar guard cuts C_m by about 1% at h = 0.1 mm (48% at 1.6 mm) [C], so guards of the FE25 kind waste channel width. A plane between the conductors removes the coupling.
- **Test:** crosstalk coupon with an SW-like aggressor and victims on L1 with and without a guard, and on L3.

**SY12. Node–loop crossover distance sets the halo** — *new, S.*
- **Mechanism:** for each aggressor cell, find where capacitive pickup Z_v·C_m·dV/dt (∝ 1/r³) overtakes magnetic pickup M·di/dt (∝ h²/r⁵ over a plane):

  r* = 3·η0·h·√((A_M/A_E)·(di/dt)/(Z_v·dV/dt))

  Beyond r* the node sets the halo (area × swing, 1/r³); inside it the loop does.
- **Principle:** P2 broken by P3.
- **Why:** halos sized from magnetic coupling alone miss the electric term. Over a 0.1 mm plane it dominates beyond 2.2 mm for a 1 kΩ victim and 9.7 mm for 50 Ω [C].
- **Test:** E- and H-probe near-field scans at 3, 5, 10 and 20 mm on a buck coupon with 50 Ω and 1 kΩ victim terminations.

## D. Mirror symmetry and balance

**SY13. Symmetry declarations on the physics graph** — *new, M.*
- **Mechanism:** the IR declares symmetry groups as permutations of ports and bodies: pair Z2, H-bridge Z2×Z2, 3-phase C3, N-phase interleaved CN, paralleled parts S_N. The extractor then:
  - reports the residual ‖PXPᵀ − X‖/‖X‖ for X = R, Lp, C;
  - splits any edit into symmetric and antisymmetric parts;
  - attributes the antisymmetric residual to features by adjoint.
- **Principle:** P4.
- **Why:** this generalizes PC16 and DR44 from pairs to every symmetric structure. It checks the symmetry of the operator, not of the drawing.
- **Test:** plant asymmetries (one-sided via, unequal pad, one-sided pour) in pair, bridge and 3-phase layouts, and measure localization accuracy.

**SY14. Mode conversion as one budget with an equivalent-skew currency** — *sharp, S.*
- **Mechanism:**
  - Merge Bal and Vcm into one quantity, mode conversion, with a level index: pair vs its reference, or board vs world.
  - Express every source in one currency: geometric asymmetry (Δχ, the change in current-division factor χ = C1g/(C1g+C2g)) and skew alike, in dB or as equivalent skew Δt_eq = 2|Δχ|/(π·f).
- **Principle:** P4.
- **Why:** common practice budgets skew in ps and asymmetry nowhere. A 10 µm width mismatch (−41 dB, about 6 ps at 1 GHz) can outweigh a whole skew allowance, while copper beyond 3h is negligible [C].
- **Test:** rank conversion sources on 20 pairs; compare with openEMS Scd21.

**SY15. Imbalance-step ledger for pairs and connectors** — *sharp, M.*
- **Mechanism:**
  - Compute χ(z) along each pair and each single-ended net, against the plane and against the world, from 2-D cross-sections.
  - Common-mode sources are the steps Δχ, summed with phase e^(−jβz), plus a velocity-mismatch term in microstrip.
  - An asymmetric section that opens and closes within ℓ ≪ λ/2π costs ∝ βℓ·Δχ. One that reaches a connector costs Δχ in full.
  - At connectors, assign return pins so that χ_board ≈ χ_cable: "unbalance matching" (Watanabe et al. [S]).
- **Principle:** P4.
- **Why:** FE35's "accumulate imbalance" counts uniform asymmetry that does not convert, and misses the step at the cable.
- **Test:** openEMS Scd21 and cable CM current on 6 layouts with planted steps.

**SY16. Antiphase node pairing, the electric figure-8** — *new, S.*
- **Mechanism:**
  - Full bridges with complementary switching, push-pull stages, class-D outputs and 180°-interleaved phases have switch nodes in antiphase.
  - Place those nodes adjacent, with equal copper area over the same plane. Their voltage-area moments cancel, at every harmonic for complementary switching and at odd harmonics for interleaving.
  - Budget the area imbalance the way XD11 budgets current imbalance.
- **Principle:** P2c (the dual of mirrored loops), P4.
- **Why:** XD11 and LA35 cancel loops but have no node twin, and node coupling is what remains over a plane (SY10).
- **Test:** near-field E scan and cable CM current for adjacent equal-area vs separated layouts of a full bridge.

**SY17. Null-plane placement for cancelled aggressors** — *sharp, S.*
- **Mechanism:**
  - After `cancel` (mirrored halves), make the halo anisotropic and place victims on the mirror plane. It is an exact null, and −20 dB at 10% imbalance [C].
  - Score `cancel` on far-field moment (κ-weighted cable coupling), not on halo radius.
- **Principle:** P4 (odd sources are null on their mirror plane).
- **Why:** with 3 mm halves the halo radius shrinks only 2% over a plane, while the field at 100 mm falls 22 dB [C]. S5's "pack tighter" is the wrong use.
- **Test:** PEEC M at null and off-null positions; near-field scan of a dual-cap buck.

**SY18. Feed topology from its symmetry group (Curie check)** — *new, S.*
- **Mechanism:**
  - For N paralleled parts, compute the automorphism group of the feed-and-return network (graph plus resistances).
  - Sharing is equal only within one orbit, so report the orbits as the sharing guarantee.
  - Offer a transitive feed (binary tree, star, ring) when equal sharing matters, and reverse return when pairs suffice.
- **Principle:** P4, P7.
- **Why:** reverse return equalizes only pairs, I_k = I_(N+1−k), with ratio 2.4. A binary tree gives 1.000, and 1.067 with one branch 20% off [C].
- **Test:** FD current share on 5 paralleled-FET and LED layouts; orbit count against measured spread.

**SY19. Moment-matching order for matched groups** — *combo, S.*
- **Mechanism:**
  - Score matched devices (bridge arms, gain pairs, mirrors, sense resistors) by how many spatial moments of their layout coincide: order 1 is common centroid; order 2 adds equal second moments (ABBA/BAAB).
  - Apply this to every gradient field the solvers make: temperature, plane voltage, stray B, etch density.
- **Principle:** P7.
- **Why:** TM14 covers thermal gradients only, and only to order 1. The same rule cancels DC plane gradients for precision ADCs ([worked case C](../../topics/physics/worked-thought-experiments.md)) and field gradients for sense loops (XD76).
- **Test:** FV and sheet gradients on 3 precision layouts; residual mismatch against moment order.

**SY20. Etch-loading symmetry around pairs** — *new, S.*
- **Mechanism:** keep copper density within about 3h equal on both sides of each fast pair, or make one-sided copper symmetric, so that etch loading does not skew leg widths.
- **Principle:** P4.
- **Why:** a 10 µm leg-width mismatch converts −41 dB [C], more than the field effect of any nearby copper (−60 dB at 2h). Whether one-sided copper actually biases width is unmeasured.
- **Test:** measure leg widths on a coupon with one- and two-sided pours at 1h–5h; Scd21.

## E. Apertures and islands

**SY21. Babinet aperture–island critic** — *combo, M.*
- **Mechanism:** one critic for slots, merged antipad rows, gaps between stitching vias, can seams and floating copper fingers. It computes:
  - polarizability ∝ ℓ³/ln(4ℓ/g) for a slot and d³/6 for a hole (Bethe [S]);
  - the half-wave resonance c/(2ℓ√ε_eff), shared by a slot and its complementary island;
  - driving-point L from Booker, (η0²/4)·C_strip, cross-checked against the slotline formula (within 6% [C]).
- **Principle:** P2a.
- **Why:** this is one physical object spread over FE2, FE4, FE32, XD83, XD80 and PW11. Merging N holes into a slot multiplies leakage by roughly N²·(p/d)³.
- **Test:** openEMS S21 through a seam and a slot against prediction; resonance of a floating finger.

## F. Gauge

**SY22. Every voltage names its loop** — *new, S.*
- **Mechanism:**
  - A budget "V between A and B" must name its measurement path: the sense wires, or the ADC reference route.
  - Critics evaluate φ(A) − φ(B) − jω∫A·dl along that path. The sum is gauge-invariant even though its parts are not.
  - A budget without a loop is a validation error, like LA1's half-port.
- **Principle:** P5.
- **Why:** at frequency, "the voltage between two ground points" depends on the path. PW41's Kelvin L_err of 0.55–0.87 nH, which changes with sense routing, is exactly this.
- **Test:** count ambiguous budgets on 5 boards; compare loop-EMF predictions with probes routed two ways.

**SY23. Gauge-invariant ledger attribution** — *sharp, S.*
- **Mechanism:**
  - Attribute a loop's or port's spend to segments by sensitivity (adjoint ∂y/∂geometry) or by Shapley values over segment edits, not by partial-inductance size.
  - Flag ledger rows whose top spender changes between conventions.
- **Principle:** P5.
- **Why:** partial inductance is gauge-fixed accounting (A → 0 at infinity). The segment with the largest partial L need not be the edit that helps most, and the LLM acts on "top spenders".
- **Test:** on 10 hot loops, compare both rankings with the edit that actually lowers L most.

## G. Images, scales and lattices

**SY24. Image-lattice kernel library** — *combo, S.*
- **Mechanism:** one library of image lattices for bounded sheets, with the sign set by the boundary type:
  - Neumann, adiabatic or open cavity edge: +;
  - Dirichlet or shorted edge: −.
  
  It serves IR drop, decap reach (XD113), thermal (TM2), slit prices near edges (SY6) and cavity Green's functions.
- **Principle:** P3.
- **Why:** shift-invariant kernels were 2–3× off near edges in thermal, and XD112's PDN and IR kernels have the same flaw.
- **Test:** against FD near edges for IR drop and decap reach on 5 outlines.

**SY25. ℓ_d map: image validity per structure** — *sharp, S.*
- **Mechanism:**
  - Per band, compute ℓ_d = R_s/(ωμ0) for each reference layer.
  - Compare it with each structure's scale: h for a trace return, loop size for a commutation loop, region size for an ADC ground.
  - Pick image PEEC, a resistive sheet or a thin-sheet eddy solve per structure and band.
- **Principle:** P6.
- **Why:** a 1 oz plane starts to mirror a 5 mm loop at 12 kHz (about 5% mirrored; half at ~93 kHz for h = 0.1 mm), but a trace return at h = 0.1 mm forms only above 0.6 MHz [C, rt_sheet_return]. One f_x per stackup mislabels both.
- **Test:** thin-sheet eddy solver against image PEEC across these scales.

**SY26. Corner-type-aware rounding** — *sharp, S.*
- **Mechanism:** classify each copper corner.
  - **Concave:** current crowds as r^(−1/3), and the corner is E-free. Fillet concave corners on pulse, fuse and ESD paths.
  - **Convex:** E crowds in the 270° gap, and the corner carries no current (r^(+1)). Round convex corners on HV nets, and chamfer convex pour corners freely.
- **Principle:** P6 plus conductor/dielectric complementarity.
- **Why:** PW18 and TM22 treat the two effects separately. The duality says they live on opposite corners.
- **Test:** FD bends plus an HV field solve; pulse heating and inception against corner type.

**SY27. One antenna-mode map, both CM mechanisms** — *combo, S.*
- **Mechanism:** from FE3's antenna-mode solution (K_ext, σ_ext), one solve per connector pair, read two couplings:
  - current-driven coupling ∝ h·K_ext(x)·cos θ for every trace and loop;
  - voltage-driven coupling ∝ ∫V dA·σ_ext(x) for every node, pad, heatsink and SW pour.
  
  The edge law is Maxwell's 1/√(1−(2x/W)²) [C].
- **Principle:** P1, P6.
- **Why:** MREMC-style budgets treat traces as current-driven and apply the voltage-driven form mainly to heatsinks. SW pours near edges are voltage-driven antennas.
- **Test:** against openEMS on 3 boards; ranking of the top CM contributors.

**SY28. Designed cuts that steer current off a measurement** — *new, M.*
- **Mechanism:** given the aggressor's flow ψ_a and the measurement's lead field ψ_lead, search for cuts that reduce R_s∫K_a·K_lead dA while keeping the loss and return-path budgets. Each cut is priced at ΔJ = (π/4)R_s·Δψ_a·Δψ_lead, with sign.
- **Principle:** P1, P2b.
- **Why:** "split the ground" is folklore because nobody computes which cut helps. This computes it, and also says when exclusion is unnecessary (orthogonal flows).
- **Test:** on 5 mixed-signal boards, predicted against FD change in measured offset; compare with a full split.

**SY29. Weave-lattice commensurability check** — *sharp, S.*
- **Mechanism:**
  - Treat glass cloth as a 2-D lattice with warp and weft pitches.
  - Score each long pair segment's angle against directions perpendicular to strong reciprocal-lattice vectors: the axes, and for near-square weaves with strong crossings the cell diagonal atan(p_y/p_x).
  - Prefer incommensurate angles.
- **Principle:** P4 and P6 (lattice symmetry, Weyl equidistribution).
- **Why:** FE42 allows up to 45°. In a toy square-weave model with a crossing term, 45° gives 1.5 ps per 2 in against ≤0.5 at other angles [C].
- **Test:** skew measurements or a 3-D weave model at 0°, 10°, 22° and 45° on 1080, 2116 and 1067 cloth.

**SY30. Reverse-drive near-field scan** — *new, S.*
- **Mechanism:** drive the victim port with a generator and scan the board with a near-field probe. By reciprocity the map equals the victim's pickup from a probe-like source at each point, so one scan replaces point-by-point injection.
- **Principle:** P1.
- **Why:** it gives F4 susceptibility data (gap 1) for the cost of an emission scan.
- **Test:** compare with direct injection at 10 points on a coupon (±2 dB).

**SY31. Scaled coupons by electromagnetic similarity** — *new, M.*
- **Mechanism:**
  - Keep copper thickness and εr, scale every other length by s (2–4×), and measure at f/s.
  - Then R = R_s·N□, ωL, ωC, kℓ and the image group ℓ·ω·μ0/R_s are all unchanged, so every impedance and coupling of the original is reproduced.
  - Only t/δ and the relative copper thickness differ.
- **Principle:** P6.
- **Why:** sub-millimetre features over 0.1 mm prepreg are hard to build and probe accurately. Scaled coupons on standard laminate are cheap and easy to probe, which helps the calibration programme (gap 1). Parts do not scale, so mounting-inductance coupons stay 1×.
- **Test:** 1× and 3× hot-loop and slot coupons; agreement of impedance at f and f/3.

**SY32. Duality generator for rules and operators** — *new, S.*
- **Mechanism:**
  - Apply P2 mechanically to the rule and operator catalog: loop → node (L→C, ψ→φ, current→voltage, loop image→charge image), cut → bridge, slot → island.
  - Flag where the plane breaks the dual (P3), and send each new dual to the solvers for a verdict.
  - This lens's examples: SY8, SY11, SY16, SY21, SY26.
- **Principle:** P2, P3.
- **Why:** duals are otherwise found one at a time. A generator finds the missing half of the vocabulary and the asymmetries a plane creates.
- **Test:** generate duals for 40 operators and count the physically valid new ones after solver checks.
