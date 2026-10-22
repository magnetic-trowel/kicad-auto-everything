# Lens LS ideas: locality, causality, scales and the circuit limit (LS1–LS32)

Ideas from the lens on scales and the circuit limit. Principles P1–P7, the derivations and the checks are in [lens-ls](../../topics/physics/lens-ls.md). The principles are:
- P1 quasi-static limit;
- P2 impedance-level split;
- P3 conductor imperfection (plane resolution ℓ_m = δ²/t, receding image);
- P4 insulator relaxation;
- P5 locality and decay classes;
- P6 causality;
- P7 scale separation.

Numbers tagged [C] come from [ls_thin_sheet.py](../../../tools/research/physics/ls_thin_sheet.py), [ls_post_lattice.py](../../../tools/research/physics/ls_post_lattice.py) and [ls_regime_map.py](../../../tools/research/physics/ls_regime_map.py). Other ids refer to the [physics-first catalog](README.md); CT, SY, TH, IN and CD ids refer to the sibling lens files.

Tags: **new** (not in the catalog, the sibling lenses or the corpus), **combo** (known pieces, new combination), **sharp** (an existing idea given an exact form, a number or a test). Effort: S (days), M (weeks), L (months).

**Top five:** LS1 complex-image PEEC, LS8 wire-medium model, LS5 impedance-level classifier, LS15 non-perturbative trigger, LS12 ℓ–f regime plane. **Quick wins:** LS7 critical-length family, LS32 ESD path threshold.

## A. Planes in the transition band (P3)

**LS1. Complex-image PEEC for the transition band.** — *sharp, S; P3.*
- **Mechanism:** in the image-plane PEEC (SIM16), replace the perfect image at depth h with N images at complex depths h + p·e·u_i/β, where p = 2R_s/(jωμ0) and the weights c_i come from a contour-rotated Gauss–Laguerre rule (N = 4–6, φ ≈ 20–25°, β = 2). The existing ln, Neumann and coaxial-loop formulas accept complex distances. One evaluation per frequency then gives R(f) and L(f) from the resistive (Carson) end to the mirror limit.
- **Beats:** the perfect image errs by up to 68–79% in L′ between 10 kHz and 10 MHz. One complex image errs 13–33%; 4–6 images err 0.4–3.5%. The 3-D coil of pw_eddy is reproduced exactly out of sample [C]. Cost is N image evaluations (ms), against seconds to minutes for a meshed thin sheet. This closes research-gaps gap 2 for intact planes. SY25 picks solvers by ℓ_d but has no closed form.
- **Test:** compare against meshed-plane PEEC and FastHenry (internal only) on 20 loops from 10 kHz to 10 MHz. Target: L within 3%, R within 10%.

**LS2. Return-width halo per band.** — *sharp, S; P3.*
- **Mechanism:** over an intact plane, the return of an aggressor harmonic at f has a width of about 2h + ℓ_m(f), capped by the plane width. Draw it as one halo per band. Any victim reference tap inside the halo of an aggressor band gets a shared-impedance budget row.
- **Beats:** RG48 renders return currents with four solves; this is a closed form. For a 0.5 oz L2 at 0.1 mm, the 500 kHz return of a buck is confined to about 0.7 mm and its 20 kHz content to 12 mm. Mains-frequency content (ℓ_m = 5 m) covers the whole board [C].
- **Test:** compare halos with return-share maps from ls_thin_sheet, vo_return_spread and a meshed solve on 5 boards.

**LS3. Receding-image kernel for transients.** — *new, S; P3, P6.*
- **Mechanism:** after a current step, a thin plane acts as an image receding at w_s = 2R_s/μ0 (782 m/s for 1 oz) ([Liu & Belcher eq. 1](https://arxiv.org/abs/0712.0182)). The coupling to a victim is then M(t) = M_image(depth h + w_s·t). A structure of size a stays shielded for about a/w_s: 6.4 µs for a 5 mm loop and 128 ns for an h = 0.1 mm trace image at 1 oz [C].
- **Beats:** pulse coupling from inrush, ESD, hot-plug and load steps no longer needs many frequency-domain harmonics. The kernel is exact for thin sheets and also says when PW24's shield credit holds for a pulse of length T: only while a > w_s·T.
- **Test:** compare M(t) against a time-stepped thin-sheet PEEC or transient FEM for 3 aggressor–victim pairs.

**LS4. Thin-sheet Carson term in the ledger.** — *sharp, S; P3.*
- **Mechanism:** in the transition band (h ≪ ℓ_m ≪ W), charge the return with R′ = ωμ0/4 (about 2 mΩ/mm per MHz) and L′ ≈ (μ0/2π)·ln(ℓ_m/r_eq). Neither depends on the plane's copper weight. Use these for audio, ripple and low harmonics.
- **Beats:** no solve is needed for low-frequency return loss. It also corrects the intuition that heavier plane copper lowers transition-band loss: heavier copper localizes the return instead (ratio to ωμ0/4 is 0.98–0.99 at 1 kHz for 0.5–2 oz) [C].
- **Test:** pw_xsec with finite planes; bench R(f) of a trace over a 1 oz and a 2 oz plane from 1 to 100 kHz.

## B. The impedance-level split and the critical length (P2)

**LS5. Impedance-level classifier with Z0 targets.** — *combo, S; P2.*
- **Mechanism:** per structure and band, compute four numbers: θ = ωℓ/v, m = Z0/Z (Z from the net passport's V/I, Z0 from the cross-section), ε_L = θ·m and ε_C = θ/m. Classify the structure:
  - m > 1: L-critical. Move Z0 down: lower h, widen, stack.
  - m < 1: C-critical. Move Z0 up: narrow, raise, void the plane.
  - m ≈ 1: matched. With resistive ends a short line is a pure delay to first order at any m; matching removes the second-order error.
  
  If Z falls outside the PCB Z0 span (about 0.4 Ω for a 50 mm plane pair at 0.1 mm, up to ~170 Ω for a thin trace on a 1.6 mm two-layer board), flag it as "unmatchable". The remedy is then structural: a plane pair, parallel paths, a shorter ℓ or a void.
- **Beats:** name-based roles (PW1) and threshold numbers (CT26's K_C and K_L) say what is critical. This one ratio also says which knob to turn and in which direction, and it contains PW2's Z0* = V/I.
- **Test:** on 30 nets from 5 boards, rank structures against PEEC plus SPICE, and check that moves toward Z0 = Z lower the LII.

**LS6. Delay-only certificate for matched nets.** — *new, S; P2, P6.*
- **Mechanism:** where source and load satisfy |m − 1| < δ (series-terminated or matched pairs), bound the amplitude error by (θ²/8)(m − 1/m)² plus the tolerance reflection. Then skip the transmission-line simulation and budget only delay and skew.
- **Beats:** the exact two-port has zero amplitude error at any length when matched (§2 of the topic doc) [C]. USB impedance tolerance barely moves the eye ([worked-thought-experiments](../../topics/physics/worked-thought-experiments.md)); this turns that one observation into a gate that removes SI simulation from most matched nets.
- **Test:** compare certified nets with IBIS/SPICE eyes on 50 nets and count false certificates.

**LS7. Critical-length family instead of t_r/6 vs t_r/2.** — *sharp, S; P2, P6.*
- **Mechanism:** replace "review at t_r/6, terminate at t_r/2" with T_crit/t_r = f(R_s/Z0, Z0·C_L/t_r, overshoot budget), taken from an exact lossless-line ramp response and driven by IBIS driver impedances.
- **Beats:** this settles a contested rule ([myths](../../topics/rules/myths-and-contested.md)) [C]:
  - t_r/6 is about a 10% budget with typical drivers (R_s/Z0 = 0.3–0.6).
  - t_r/2 is a budget of 20% or more with weak drivers.
  - Strong drivers (0.1) overshoot 83% at t_r/2.
  - Series-matched lines never overshoot.
- **Test:** predicted overshoot against SPICE on 100 nets with IBIS models.

## C. Decaps and stitching as one wire medium (P5)

**LS8. Wire-medium model for decap and stitching fields.** — *new, S; P5.*
- **Mechanism:** one module computes γ² = Z_s·(jωC′ + n/Z_post) and ω_p² = n/(L_post·C′). It outputs three things:
  - the screening length λ(f) = v/√(ω_p² − ω²);
  - the anti-resonance f_p, the k = 0 mode, including the post's cell spreading;
  - mode shifts to √(f_mn² + f_p²).
  
  Posts are decaps (L_c, C, ESR) or vias (Belov's L_post).
- **Beats:** four results become one formula: XD113 reach, the Belov stitching check, the lumped anti-resonance and decaps raising cavity modes. The lattice agrees within 0–3% [C]. It replaces "stitch at λ/20", "decap within N mm" and separate anti-resonance calculators.
- **Test:** compare with a PDN tool or Palace on 3 stackups with real decap sets, then with bench Z(f).

**LS9. Plasma-frequency band plan.** — *new, S; P5.*
- **Mechanism:** make each plane pair's f_p a frequency-plan variable (S8, DR36, FE13).
  - GND–GND: choose the stitching pitch so f_p clears the highest protected band. With 0.3 mm vias and a 2.45 GHz band, 11 mm gives 3.03 GHz (+24%), 12 mm gives 2.74 GHz (+12%) and 13 mm gives 2.50 GHz (none) [C].
  - GND–PWR: choose decap density and ESL so the anti-resonance avoids clock harmonics and radio channels, or damp it with ESR at f_p ([lens-th](../../topics/physics/lens-th.md)).
- **Beats:** today the pitch is "λ/20" and anti-resonances are discovered after layout. f_p is a closed form in pitch, via radius, ESL and d.
- **Test:** compare f_p with cavity-model and full-wave first resonances on 5 boards; count harmonic coincidences before and after planning.

**LS10. Lumped-PDN validity gate.** — *sharp, S; P5.*
- **Mechanism:** a lumped "all decaps in parallel" model is valid only in two places: where λ(f) exceeds the board (near f_p), or below SRF, where the slow-wave wavelength is long. Flag any target-impedance analysis whose band lies between SRF and f_p with λ smaller than the board.
- **Beats:** tells when decap position matters; on thick pairs that is most of the decoupling band. It also reconciles "location matters" with "location doesn't matter" ([decoupling-pdn](../../topics/rules/decoupling-pdn.md)).
- **Test:** lumped vs lattice Z_in on 10 configurations; plot the error against λ/board.

**LS11. Point-load PDN inductance as the decap and stackup objective.** — *sharp, S; P5, P2.*
- **Mechanism:** an IC power via cluster of equivalent radius r_eq inside a decap field sees L_in ≈ (μ0d/2π)·ln(1.12λ/r_eq), valid when L_c/(μ0d) ≫ 1. Choose the levers by their weight:
  - d is linear;
  - cluster radius is logarithmic;
  - ESL is logarithmic, entering through λ.
  
  Z_target ≥ ω_max·L_in then sets the maximum d, a closed-form input for stackup synthesis (DR30, PW28).
- **Beats:** with the same decaps, L_in is 85 pH at d = 0.1 mm and 690 pH at 1 mm, with d ln L_in/d ln L_c = 0.07–0.17 [C]. Shopping for low-ESL decaps buys little next to a thinner dielectric or a wider via cluster.
- **Test:** compare with lattice or PEEC with discrete decaps on 3 boards, then with vendor PDN measurements.

## D. Regime selection, order and representation (P1, P7)

**LS12. The ℓ–f regime plane as the regime selector.** — *new, M; P1–P7.*
- **Mechanism:** a log size–log frequency map whose boundaries are ℓ = δ, δ²/t, λ/10, λ/2, λ/2π, λ_th, √(α/ω), λ_pdn(f), 1/k_p and v·t_r/6. Each structure is a segment: its scales run from h to its size, its band from the fundamental to the knee. The cells it crosses choose the representation (ideal, lumped R/L/C, complex images, line, wire medium or modes, antenna, thermal kernel) and the solver rung.
- **Beats:** replaces design-reasoning's fixed band table and RG2's 14 groups with four primitive ratios. One object serves the LLM's explanations, the ledger's Regime type (LA11, given a scale coordinate) and the SIM4 dispatcher.
- **Test:** dispatch 100 structures, then check the chosen representation against F3 on 10 of them.

**LS13. Victim-relative expansion order.** — *new, S; P7.*
- **Mechanism:** n* = ⌈ln(B/S)/ln ε⌉, with S the victim's signal, B its budget and ε its largest coupling parameter. n* decides which physics packs run. At n* ≥ 3 the system adds thermal EMF, plane gradients from foreign currents, leakage and dielectric absorption.
- **Beats:** digital needs order 1, 16-bit order 3 and 24-bit order 4 at ε = 0.01 [C]. It explains why precision analog is hard at low frequency, and it keeps compute off digital nets.
- **Test:** on 10 mixed-signal boards, check that n* flags every mechanism a full analysis finds binding (worked case C).

**LS14. Truncation-error σ for every evaluator.** — *new, S; P7.*
- **Mechanism:** beside its residual σ (SIM8), every evaluator reports the size of its first neglected term:

  | Evaluator | First neglected term |
  |---|---|
  | lumped L or C | θ²/6 |
  | quasi-static PEEC | (kℓ)² |
  | perfect image | ℓ_m/h |
  | thin sheet | t/δ |
  | continuum decaps | μ0d/(π·L_c) |
  | Hammerstad | t/h |
- **Beats:** SIM2's validity domains are empirical ranges. These estimates can be computed anywhere, including outside the calibration hull, and they name the rung to escalate to.
- **Test:** predicted against actual error versus F2/F3 on 50 structures.

**LS15. Non-perturbative trigger.** — *new, S; P1, P2.*
- **Mechanism:** when ε_L·Q ≥ 1, ε_C·Q ≥ 1 or any ε ≥ 1, stop adding parasitic budgets. Switch that structure to circuit-plus-network co-simulation (C2) or to a modal model (cavity, cable or ring modes).
- **Beats:** linear budgets fail for a slow 48 V bridge (DR11), and the LC-step model predicts about 100% overshoot regardless of L. Both are a series diverging. The trigger says where this will happen before it does; on RB4's hot loop, ε_L = 0.39 with a ring Q of 30–170 [C].
- **Test:** on the worked cases and 10 converter boards, compare additive verdicts with co-simulation inside and outside the trigger.

**LS16. Causal stackup model.** — *sharp, S; P6.*
- **Mechanism:** fit each laminate's single datasheet Dk/Df point to a wideband Debye (Djordjevic–Sarkar) model. Evaluate Z0, delay and loss at each net's knee and at the calibration frequencies, and flag any number computed with 1 MHz values.
- **Beats:** FR-4 Dk drifts −2.93% per decade, which equals −(2/π)·tanδ·ln 10. Between 1 MHz and 5 GHz, Z0 shifts +5.4% and delay −5.1% [C]. TM35's tolerance budgets and coupon calibration (gap 1) inherit the error.
- **Test:** coupon TDR and VNA impedance predicted with the causal model against a constant-Dk model.

**LS17. Loss-length gate.** — *sharp, S; P6.*
- **Mechanism:** ℓ_loss = c·t_r/(3.08√εr·tanδ). Below it, geometry sets the edge. Above it, the material does, so the lever becomes laminate, equalization or a shorter route.
- **Beats:** the gate tells the system when to propose a material ECO instead of a geometry tweak. ℓ_loss is 235 mm at 100 ps and 82 mm at 35 ps on FR-4, and 1.3 m and 0.45 m on low-loss laminate [C].
- **Test:** predicted line rise times against channel simulation on 10 SerDes nets.

## E. Insulators and slow processes (P4, P6)

**LS18. Surface charge-relaxation regime for guards and HV DC.** — *new, S; P4.*
- **Mechanism:** per insulating gap, τ_e ≈ ε_eff·g/σ_s, with σ_s taken from a humidity and contamination class.
  - Below 1/(2πτ_e) the surface potential follows conductivity. Guards must then be driven to equal potential, and HV DC stress follows contamination, so the fix is grading or coating.
  - Above that frequency the surface behaves capacitively.
- **Beats:** the Ins basis quantity ([rule-basis-set](../../topics/physics/rule-basis-set.md)) has a leakage ratio but no regime. A 1 mm gap has τ_e from 23 µs (humid, with residue) to 2.4 s (clean, dry) [C, assumed σ_s]. The same gap can be capacitive in the lab and resistive in the field.
- **Test:** SIR comb coupons at 40% and 85% RH under DC plus AC; measure the crossover.

**LS19. Laminate dielectric absorption near high-Z nodes.** — *new, S; P6, P4.*
- **Mechanism:** Kramers–Kronig pairs the laminate's low-frequency loss with slow polarization. For integrators, sample-and-hold stages and electrometer inputs, budget the memory error as ΔV ≈ DA × (C_laminate/C_total) × V_step. Levers: a void under the node, a PTFE island, a guard.
- **Beats:** research-gaps gap 12 lists dielectric absorption as unexamined. TH14 covers its noise, not its memory.
- **Test:** step-and-hold on coupons with and without a void under the node.

## F. Locality in the placer and optimizer (P5, P7)

**LS20. Decay-class-aware interaction lists.** — *sharp, S; P5.*
- **Mechanism:** every placer kernel carries a decay class and a length, and the class sets the cut-off:

  | Class | Examples | Cut-off |
  |---|---|---|
  | screened | thermal λ, decap λ, L_T | about 3ℓ |
  | evanescent | stripline, below cut-off | b/π |
  | algebraic | (h/D)², r⁻³, r⁻⁵ | where the budget is met (LA25) |
  | diffusive | — | √(αt) |
  | wave | — | none; go modal (LS21) |
- **Beats:** XD112, OP24 and SY24 supply the kernels but not class-driven cut-offs. With the class, list sparsity and the meaning of "close" (r/ℓ < 0.5) follow automatically.
- **Test:** runtime and objective error against full N² evaluation on 5 boards.

**LS21. Mode-shape coordinates above cut-off.** — *combo, S; P5.*
- **Mechanism:** above a pair's f_p or first mode, score each source (fast via, switch node) by Σ |φ_mn(x)|²·S(f_mn)·Q_mn. Place sources at the nodes of the dominant modes and dampers or posts at the antinodes (TH4).
- **Beats:** open edges are antinodes of every mode, which is a second reason to keep fast vias off board edges. Distance rules give way to position in the cavity regime. FE28 moves vias by eigenvalue gradient, not sources by mode shape.
- **Test:** cavity-model excitation against source position on 3 boards, with a full-wave check.

**LS22. Homogenization validity ratios.** — *sharp, S; P7.*
- **Mechanism:** before using an effective medium (Rayleigh perforation, a Peaceman via, wire-medium stitching, a hatched plane, a thermal-via array), compute its ratio: L_T/p, p/λ_d, p/h or p/λ_th. Homogenize only when the ratio is ≪ 1.
- **Beats:** via fields have L_T/p ≈ 0.4–1 (1.05 mm at 1 mm pitch). That is why the edge rows carry the current and averaged models fail (XD22, XD108, PW13).
- **Test:** homogenized against discrete solves for 20 via fields and 10 stitching lattices across the ratio.

**LS23. Physics-scaled multigrid.** — *combo, M; P7.*
- **Mechanism:** each optimizer level's grid follows the shortest kernel length active at that level: λ_th ~ 40 mm, λ_pdn 10–25 mm, 1/k_p ~ 7 mm, h, ℓ_m(f_sw). Homogenized coefficients pass up and boundary values pass down (XD109). This replaces JPR16's fixed 2 mm and 0.5 mm levels.
- **Beats:** each level resolves exactly the physics it optimizes, and shorter-scale terms enter as homogenized parameters.
- **Test:** J against CPU time, compared with fixed multigrid, on 10 boards.

**LS24. Scale-ordered decision schedule.** — *combo, M; P5.*
- **Mechanism:** order decisions by the spatial scale they act on, and by least slack τ (DR17) within each scale:
  1. system: connector edges, cable points, enclosure;
  2. board: stackup, plane partition, cell placement;
  3. cell interior;
  4. feature.
- **Beats:** far-field budgets see only the low-order moments of the sources. That explains why, in the one worked EMI case ([fields-emi-budget](../../topics/physics/fields-emi-budget.md)), removing a slot or split beat edge-rate and series-R tweaks by 20–35 dB, and it gives JPR50's outer loop a physical basis.
- **Test:** on 5 boards, coarse-first against τ-only ordering; compare spend and backtracks.

**LS25. Cells as multipole particles.** — *combo, M; P5.*
- **Mechanism:** optimize each cell's interior for its local budgets and for small external moments: dipole with image, net external charge Σ C_ext·V ([lens-ct](../../topics/physics/lens-ct.md)), and heat. The board placer then treats cells as particles carrying those moments and couples them through far-field kernels. Near pairs are evaluated directly, as in an FMM split.
- **Beats:** DR22's cells become a computational unit, not only an explanation, and far interactions cost O(N).
- **Test:** objective error and runtime at 50–300 parts.

**LS26. Radiator selector by electrical size.** — *sharp, S; P1.*
- **Mechanism:** per band, pick the antenna from size against λ. Candidates:
  - cables (λ/2 at 75–150 MHz for 1–2 m);
  - board ground (resonant from about 1–1.5 GHz at 100 mm);
  - heatsinks;
  - slots (λ/2 at ε_eff);
  - cavity edges above f_p.
  
  Then choose MREMC, edge-radiation, slot or full-wave models to match.
- **Beats:** [fields-emi-budget](../../topics/physics/fields-emi-budget.md) uses MREMC throughout. This makes the model choice explicit and band-dependent.
- **Test:** against full-wave dominant-radiator analysis on 5 board-and-cable setups.

**LS27. Two-timescale condition for the joint optimizer.** — *new, S; P7.*
- **Mechanism:** two-timescale stochastic approximation requires the inner loop (re-tightening, prices) to converge between outer moves: η_outer/η_inner → 0. Monitor the inner residual after each outer move, and slow the outer loop when topological events cluster.
- **Beats:** JPR13, JPR17 and JPR18 use heuristic hand-off thresholds. Singular-perturbation theory says when slaving the fast variables is valid.
- **Test:** convergence and final J with and without the adaptive ratio on JPR's synthetic boards.

## G. What each conductor is doing (P1, P3, P5)

**LS28. Role ladder per conductor.** — *new, S; P1, P3.*
- **Mechanism:** per body, compute five frequencies and one number:

  | Quantity | Formula |
  |---|---|
  | f_mirror(a) | R_s/(πμ0a) |
  | f_x(h) | R_s/(2πμ0h) |
  | f_skin | ρ/(πμ0t²) |
  | f_TL | v/(10ℓ) |
  | f_res | v/(2ℓ) |
  | radiation | (ka)³ at the band top |

  Label each band with a role (resistor, diffuser, mirror, line, resonator, antenna) and store it beside the [lens-cd](lens-cd.md) passport.
- **Beats:** the labels come from geometry alone, before any solve, and tell the LLM which physics applies to the copper in each band.
- **Test:** labels against solver-observed behavior on 50 bodies.

**LS29. Observable-scale evaluation of conductor jobs.** — *new, M; P1, P5.*
- **Mechanism:** evaluate a conductor's job at the scale of each budget's observable. At the same frequency, a ground plane is a mirror for a 0.1 mm-scale SI budget and an antenna arm for a 1 m cable common-mode budget. The CD passport stores job(f, ℓ_obs), and I1 attribution runs per scale.
- **Beats:** ends the single-label confusion between "the plane is a solid reference" and "the plane drives the cable". Both hold, at different scales.
- **Test:** on 5 boards, check whether per-scale attribution reorders the EMI spenders.

## H. Calibration (gap 1)

**LS30. ℓ_m coupon.** — *sharp, S; P3.*
- **Mechanism:** build a trace over a plane with Kelvin sense traces at several offsets, and measure with a lock-in from 1 kHz to 5 MHz. Fit the return width against f to ℓ_m(f) = δ²/t. The fit gives the plane's effective thickness, plating and roughness, and it validates LS1.
- **Beats:** isolates one kernel, the transition law, as research-gaps gap 1 asks.
- **Test:** the coupon itself, in 0.5, 1 and 2 oz.

**LS31. f_p lattice coupon.** — *sharp, S; P5.*
- **Mechanism:** GND–GND and GND–PWR coupons carry stitching or decap lattices at 3 pitches. Measure with a VNA at a central via: the first resonance (f_p), and the port-to-port coupling against distance below f_p.
- **Beats:** one coupon validates decap reach, stitching cut-off and the anti-resonance together (LS8).
- **Test:** f_p and decay length within ±10% of prediction.

**LS32. ESD path as a non-perturbative structure.** — *sharp, S; P2.*
- **Mechanism:** require ε_L = ω_knee·L_path/Z_clamp < 1, that is L_path ≤ Z_clamp/(2π·0.35/t_r): 0.12 nH for a 10 V/30 A clamp at 0.8 ns. Return the TVS ground through the nearest plane (0.03 nH), never through the board (1.3 nH, ε_L ≈ 11) [C].
- **Beats:** RG22 and DR47 budget the path inductance. This adds the threshold at which the parasitic becomes the circuit.
- **Test:** SPICE with TVS models across L_path, then clamp voltage on coupons.
