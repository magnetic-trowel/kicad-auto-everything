# Lens VP: variational principles and energy

**TL;DR**
- **Nature solves for the currents; the designer chooses the domain.** Each quantity the layout controls is an energy minimum over fields the copper constrains. For self-energy objectives that copper lowers (loss, loop L, thermal resistance, 1/C), layout collapses into one joint minimization that is convex in a relaxed copper density, with free gradients, certified floors and monotonicity. Couplings, single-load drops and EMI masks lack these.
- **Round 1's missing floor oracles exist and are cheap** [C]. On round 1's test pour at equal area, a closed form gives R ≥ 1.53 mΩ in 150 µs and a convex relaxation with a dual certificate gives R ≥ 1.761 mΩ. So round 1's synthesized pour (1.789 mΩ) is within 1.6% of the best possible, and the human tree (2.092 mΩ) carries 15.8% avoidable loss. A convex start also removes round 1's inductance-only local optimum (0.546 vs 0.613 nH).
- **Complementary principles give two-sided bounds** [C]. Potential and stream-function solves on one coarse mesh bracket a corner at 0.530–0.581 squares (exact 0.5587). Logarithmic capacity gives via-cluster inductance within 2%. Hashin–Shtrikman explains why Rayleigh's via-field formula only under-predicts: hexagonal fields sit within 5% of the bound, square ones up to 40% above.
- **The R–L crossover is a spectrum, not one frequency.** Half the return lies within ℓ50 ≈ R_s/(2π·μ0·f) of the trace, whatever h: 62 mm at 1 kHz and 0.12 mm at 500 kHz for 1 oz [C]. Round 1's f_x is the case ℓ = h. Converter fundamentals already return under the loop; the open regime is DC to tens of kHz near precision analog.
- **Energy is the right currency only for self terms.** These energies add, their gradients are free and their floors are provable. Couplings are interaction energies (one adjoint each); EMI limits are a maximum over frequency, not an energy.

Tags: [S] secondary, [I] inference, [C] computed by [vp_floors.py](../../../tools/research/physics/vp_floors.py), [vp_rl_band.py](../../../tools/research/physics/vp_rl_band.py) or [vp_edit_pricing.py](../../../tools/research/physics/vp_edit_pricing.py) (quasi-static, uncalibrated). Ideas VP1–VP30: [lens-vp ideas](../../ideas/physics-first/lens-vp.md).

## Key facts

### 1. The principles

| # | Principle | Statement | PCB reading |
|---|---|---|---|
| V1 | Thomson (DC) | I²R = min ∫R_s·\|K\|² over sheet currents K with the given sources. A trial K bounds R from above | Current spreads to minimize loss; added copper never raises a two-terminal R |
| V2 | Dirichlet (DC) | V²/R = min ∫\|∇φ\|²/R_s over φ fixed on the terminals. A trial φ bounds R from below | Dual of V1 |
| V3 | Maxwell, minimum magnetic energy (ωL ≫ R) | ½LI² = min ½·IᵀL_p·I over KCL currents | The return rides under the trace; coarse PEEC over-estimates HF L; added copper never raises it |
| V4 | Stationary reaction (Rumsey) | Z is the *stationary* value of Iᵀ(R + jωL)I | The transition is the spectrum of R·v = λ·L·v (eddy modes) |
| V5 | Electrostatics | CV² = min ∫ε\|∇φ\|²; Q²/C = min ∫\|D\|²/ε | C is bracketed; added copper never lowers a node's C; ε·A/h is a lower bound |
| V6 | Rayleigh quotient | ω1² = min of the energy ratio over fields vanishing at shorts | More vias never lower the first cavity mode |
| V7 | Tellegen | Σ V_k·I_k = 0 for any KCL currents and KVL voltages on one graph | ∂Z_ab/∂z_k = I_k^a·I_k^b/(I_a·I_b): a self price is a current squared |
| V8 | Poynting | −dW/dt = ∮S·dA + P_diss | Power flows in the dielectric; conductors guide, absorb or release it |
| V9 | Least action + Rayleigh dissipation | Euler–Lagrange for ½q̇ᵀLq̇ − ½qᵀPq, F = ½q̇ᵀRq̇ | A circuit is a lumped Lagrangian |
| V10 | Composite and capacity bounds | σ_eff ≤ σ(1−f) for any pattern; ≤ σ(1−f)/(1+f) for an isotropic one (Hashin–Shtrikman, HS). Capacity = exp(−minimum log energy) | Floors for perforated planes and via sets |

**The gentle limit, variationally.** A schematic is the stationary point of a Lagrangian over lumped charges and loop currents (V9). It is exact when hidden field degrees of freedom (eddy patterns, cavity modes, common-mode currents) relax much faster than the circuit or are damped, and when the energy matrices are block-diagonal between nets. Layout bends the limit: hidden modes fall in band, off-diagonal energy appears, energy leaves by retardation. Invisibility means hidden modes out of band or damped, and small interaction energies where they matter [I].

### 2. Layout as a bilevel problem

Outer: the designer's domain D (copper, parts, stackup). Inner: nature's u*(D) = argmin E(u; D).

| Class | Examples | Structure | Consequence |
|---|---|---|---|
| A. Self-energy that copper lowers | R, loop or pour L, spreading L, Σ P·T at given currents or heat; decoupling 1/C at given charge | min over D of min over the flux: ∫\|J\|²/(σ·ρ) is jointly convex in (J, ρ) | Convex floors. Free gradients (envelope theorem: a pad's pose gradient is a Maxwell-stress force). Monotone |
| A′. Self-energy that copper raises | C of a dv/dt node at given voltage | min of affine terms: concave in ρ | Monotone; floor = mandatory copper only; free gradients |
| B. Interaction | aggressor–victim M or C; one load's drop; one part's ΔT | truly bilevel | One adjoint per objective; non-convex; adding copper can hurt |
| C. Non-variational | EMI mask (max over f), thresholds, corners | many inner solves | Sensitivities per binding frequency |

Pours are class A: the adjoint is the state itself, and SIMP with p = 1 is convex, so its optimum floors every binary layout of that area. Round 1's non-convexity came from the p = 3 penalty, not the physics.

### 3. Derivations

| Round-1 result or rule | Principle | VP reading |
|---|---|---|
| "Short and wide"; R·A = R_s·l² ([power-copper](power-copper.md)) | V1 | N□ ≥ d²/A for any shape (D1) |
| Topology optimization −14.5% (OP2) | V1 | At most 15.8% was available (D1) |
| Inductance-only optimum worse than 50/50; "not self-adjoint" ([copper-shape-synthesis](copper-shape-synthesis.md), L9) | V3 | A penalty artifact (D1) |
| DC- and HF-optimal pours coincide over a uniform plane | V1 ∝ V3 | Both are ∫c·\|K\|² (c = R_s or μ0·h); they differ only where h or R_s varies |
| Loop L ∝ perimeter near a plane (0.052–0.055 nH/mm) | V3 | The energy sits under the copper: L = μ0·h·P/w |
| Via clusters: "outer size, not count" (PW32) | V10 | Capacity (D3) |
| Rayleigh's via-field formula "under-predicts" | V10 | It is the HS bound (D3) |
| Largest empty circle "±30%" (FE26) | V6 | One-sided: f1 ≤ 0.766·c/(D·√εr). Round 1's κ = 0.32–0.64 all lie below 0.766 |
| Adjoint misses a slot 30× ([solver-ladder](solver-ladder.md)) | V1 | Polarization of the edit's shape (D4) |
| f_x = R_s/(2π·μ0·h), "found four times" | V3, V4 | Two crossovers merged (D5) |
| w* at Z0 = V/I (PW2) | V3, V5 | Equipartition (D6) |

**D1. Floors for copper of area A.** By Cauchy–Schwarz,

 P = R_s·∫\|K\|² ≥ R_s·(∫\|K\|)²/A ≥ R_s·W1²/A,

where W1 = min ∫\|K\| is the earth-mover distance between sources and sinks (Beckmann 1952). With one source, W1 = Σ I_k·d_k. Round 1 used it for trees ([cross-domain-lessons](cross-domain-lessons.md) L2); Cauchy–Schwarz makes it a floor for any shape.

A tighter floor makes conductance linear in a density ρ ∈ [0, 1]. Then P(ρ) = max_v [2fᵀv − vᵀK(ρ)v] is convex. For any trial potential v, P* ≥ (fᵀv)²/max_ρ vᵀK(ρ)v, a fractional knapsack.

On round 1's pour [C, 0.1 mm grid, 105 mm², 6 A]:

| Layout or bound | R_loss |
|---|---|
| Beckmann floor (156 µs) | ≥ 1.527 mΩ |
| Convex floor (dual gap 4×10⁻⁴) | ≥ 1.761 mΩ |
| Round 1 SIMP, binary | 1.789 (+1.6%) |
| Human trunk and branches | 2.092 (+18.8%) |

- **Area sweep.** At 20–70% of free area, SIMP is 0.5–10% above the floor.
- **Slotted reference** (0.2 mm grid). The convex inductance floor is 0.524 nH.

  | Objective | Uniform start (round 1's procedure) | Convex start |
  |---|---|---|
  | Inductance only | 0.613 nH, 2.40 mΩ | 0.546 nH, 2.02 mΩ |
  | 50/50 mix | 0.604 nH, 2.05 mΩ | 0.562 nH, 1.91 mΩ |

**D2. Certified evaluation of a fixed geometry.** In 2-D, K = ∇ψ × n, so V1 becomes a Dirichlet problem for the stream function ψ with terminals and sides swapped. Conforming FEM on φ over-estimates conductance; on ψ it over-estimates resistance. Hence R_φ ≤ R ≤ R_ψ on any mesh (Prager–Synge).

For a sharp 90° bend the corner excess is bracketed at 0.483–0.610 squares with 2 cells per width, 0.530–0.581 with 4 and 0.5571–0.5603 with 32 (exact 0.5587) [C].

Decisions are certified when intervals do not overlap ([lens-in](lens-in.md)).

**D3. Vias are a capacity problem.** The spreading inductance from a via set into a plane pair of spacing d, out to radius R, is (μ0·d/2π)·ln(R/cap). Here cap is the logarithmic capacity of the set. Closed forms: r for one via, √(r·s) for two, (N·r·ρ^(N−1))^(1/N) for N on a circle, 0.590·s for a filled square.

Against round 1's grid solves [C]:

| Source | Spreading L (pH) |
|---|---|
| Round 1 | 85 / 70 / 59 / 61 / 44 / 41 / 30 / 43 / 34 |
| Capacity | 83.9 / 69.5 / 58.0 / 60.2 / 43.3 / 41.2 / 29.4 / 42.5 / 33.7 |

Capacity grows with the set, so the convex hull gives a floor (4 vias at 2 mm: ≥ 40.1 pH vs 44 realized), and vias inside the hull add almost nothing.

The same object recurs: Peaceman's sub-cell radius 0.198·Δx is e^(−γ)/(2√2), the capacity of one 5-point-grid node [I]; the stitching-lattice cut-off has the homogenized-capacity form 2π/(a²·ln(a/2πr)); the empty circle is a domain-monotonicity bound (V6).

Perforated planes:
- Rayleigh's (1+f)/(1−f) is the 2-D HS lower bound for isotropic hole patterns; 1/(1−f) bounds any pattern, and cuts along the flow attain it.
- Square lattices exceed HS by 4/15/40% at D/p = 0.8/0.9/0.95; a hexagonal lattice with the same via density stays within 5% [C].

**D4. Pricing an edit is a polarization problem.** Lenses CT and SY found this too. Cutting a small insulating hole B where the current density is K costs ΔP = R_s·KᵀM(B)K.
- A disc has M = 2·area, which is exactly round 1's estimate.
- An ellipse with semi-axis b across the flow and a along it has M = π·b·(a+b). A slit across therefore costs πℓ²/4 and a slit along costs about 0. An edge slit costs twice the interior value.
- So the area estimate misses slits by about ℓ/(2w), or ℓ/w from an edge: 30 for round 1's 6 × 0.2 mm slot.

On 16 edits [C], the area estimate gave 0.03–0.88× the exact change and the polarization estimate 0.78–0.89×. Polarizability grows with the set, so the inscribed ellipse under-prices a rectangle; that is the one-sided bias. CT adds the exact strip law; SY extends it to any objective.

**D5. The R–L crossover is a spectrum.** A thin sheet's eddy pattern of wavenumber k relaxes at λ(k) = 2R_s·\|k\|/μ0. This is Maxwell's receding image: images recede at 2R_s/μ0 ≈ 780 m/s in 1 oz copper. Confining a return within ±ℓ needs \|k\| ≳ 1/ℓ, which forms above f ≈ R_s/(π·μ0·ℓ).

2-D PEEC with exact Galerkin kernels [C; 0.3 mm trace, 100 mm plane]:
- **Containment.** The frequency at which half the return lies within ±ℓ gives f50·ℓ = 56–70 Hz·m for ℓ = 1–10 mm and h = 0.1–1.6 mm. That matches R_s/(2π·μ0) = 62 Hz·m.
- **Away from the trace.** At ≥ 100 kHz the return outside ±5 mm is only the image's own tail (1.3% at h = 0.1 mm, 20% at 1.6 mm); at 20 kHz, 32–45% lies beyond 5 mm.
- **Spectrum.** A Foster modal model of (R, L) reproduces the direct solve exactly and puts 10/50/90% of the DC-to-HF inductance drop at 17/65/360 kHz for h = 0.1 mm (f_x = 622 kHz).

Round 1's f_x merged two things: the R/ωL corner of a fixed distribution, and the frequency at which the return reaches its image width h. A return leaves a victim 5 mm away below about 12 kHz on 1 oz. Lenses SY and LS reach the same length independently ([lens-ls](lens-ls.md)).

**D6. Width as equipartition.** Copper of length l switching I and V stores ½LI² + ½CV² per cycle, with LC = (l/v)². By AM–GM this is ≥ V·I·l/v, the Poynting energy in flight, with equality at Z0 = V/I (PW2's optimum; LS derives it too). For 2 mm at 12 V, 10 A and 500 kHz it is 0.8 mW, so the parts' C_oss and package L set the real floors.

**D7. Monotonicity has a scope.** Self quantities are monotone: R and HF L fall and node C rises with any copper. Transfer quantities are not: ∂R_ab,cd/∂g_k = −ΔV_k^ab·ΔV_k^cd (V7) changes sign with the alignment of the two fields.

On round 1's human pour [C], a 1.5 mm bridge between branches cut total loss 1.0% and raised load C's drop 1%; on a 0.2 mm grid, B and C rose about 3%. Small, but the sign is wrong. "Star versus plane" is a dispute about transfer terms (also lens CD, CD24).

### 4. Convergences and synergies round 1 missed

- **φ, ψ, adjoints and prices are one object.** In V1 the potential is the Lagrange multiplier of current conservation (∂P/∂I_k = 2V_k), so "everything is a price" ([research-gaps](research-gaps.md)) is an identity. Objects 1, 2, 4 and 5 of [cross-workstream-synthesis](cross-workstream-synthesis.md) are the primal, dual, gradient and multiplier of one saddle point; (φ, ψ) also give certified error bars.
- **S7's "unified via theory" is capacity theory** (PW32, PW13, FE26, FE27, via fields; D3).
- **Cuts and holes are one formula** (OP38, OP41, XD2, SIM24, SIM25; D4).
- **Multi-load (XD62), multi-rail (OP4), DC+HF (OP5) and fixed-resistivity electro-thermal (OP11) pours are sums of compliances,** convex when relaxed: one pre-solve gives a joint floor and a warm start.
- **OP6, XD56 and the floors are one formula.** P ≥ R_s·(Σ W1,n)²/A_total, so area shares go ∝ W1,n. At the Beckmann floor dP/dA = −P/A, an elasticity of −1.

### 5. Transfers

| From | To |
|---|---|
| Topology optimization: solve at p = 1, then penalize | Non-convex OP and JPR terms; floors for OP57 |
| FEM error bounds (Prager–Synge) | SIM1's σ as certified intervals; SIM10 escalates only on overlap |
| Composite bounds (Voigt, HS) | XD108 homogenization; PW12 neck detection |
| Potential theory (capacity) | N8 via patterns, stitching, Peaceman cells |
| Power-module damping layers (Hartmann, Müsing and Kolar 2009) | Hot-loop damping as a stackup choice (VP15) |

### 6. What each conductor is doing, energetically

Per piece and band, one PEEC or sheet solve gives six numbers [I]:
- **guide:** Poynting flux along its gap;
- **store:** ½·I_k·(L_p·I)_k and ½·q_k·φ_k;
- **dissipate:** I_k²·R_k, the Poynting flux into its surface;
- **radiate:** its share of the cell's dipole moment;
- **couple:** its interaction energy with each victim;
- **damp:** its participation in each ringing mode's loss.

A budget's sensitivity to the piece is the energy density at its boundary: free for self terms, one adjoint for interactions. Lens CD builds the passport ([lens-cd](lens-cd.md)); VP supplies the energy decomposition.

### 7. Critique of round 1

1. **No principle says the physics is a minimum.** "Nature minimizes energy within the copper you draw" gives monotonicity, floors, free gradients and convexity. It should be principle 0.
2. **"Near-optimal is unprovable" is false for class A** ([research-gaps](research-gaps.md) §4). Round 1's own SIMP is certified within 1.6%. The claim stands for couplings and joint placement.
3. **The f_x convergence merged two crossovers** (D5). Gap 2 concerns DC-to-kHz returns near precision analog, not converter fundamentals; a Foster eddy model suffices.
4. **Rayleigh monotonicity was over-applied** (XD122, power-copper). It protects self terms only.
5. **The nine objects double-count** (φ, ψ, adjoints, prices) and miss capacity.
6. **Gap 3's relaxations are weak:** "copper everywhere" (0.677 mΩ) ignores the area budget and sits 2.6× below the convex floor.
7. **"One energy currency"** (S10, PW30) fits self terms only; victims and EMI masks need interaction energies or worst-frequency margins.
8. **Two misdiagnoses:** the shape factor, not the adjoint, missed cuts; the empty-circle error is one-sided.
9. **Principle 3** needs the floor N□ ≥ d²/A and equipartition; height wins because the energy sits in the gap.

## Recommendations for our system

1. **Floor stage before optimization.**
   - Compute certified floors per structure: Beckmann, convex relaxation, hull capacity, HS, empty circle.
   - Feed them to τ (DR17), pruning (JPR30), the stop rule (OP57) and infeasibility certificates (DR41).
2. **Tag every term A, A′, B or C.** Optimize A jointly and convexly first, continue into B, and give C worst-frequency sensitivities.
3. **Every class-A F2 evaluator returns a primal–dual bracket as σ.**
4. **Price edits by polarization tensors** (with CT and SY).
5. **Replace the single f_x** with ℓ50(f) against victim distance. Use Foster eddy models for kHz returns.
6. **Variational regression tests:**
   - coarse PEEC L ≥ fine;
   - FEM R ≤ true;
   - in RL extractions, L(f) non-increasing and R(f) non-decreasing.
7. **Report avoidable loss,** (R − floor)/R, for every pour.

## Conflicts and open questions

- **Floors assume fixed terminals.** As parts move, Beckmann becomes a placement term.
- **The convex floor assumes variable-thickness copper.** Minimum width and space raise the real floor (TM52 adds).
- **D5 is 2-D.** The 3-D extension follows from the receding image [I]; verify with meshed-plane PEEC.
- **The damping film needs about 0.1 Ω/sq.** Standard resistor foils start near 10 Ω/sq.

## Sources

- Classical results [S]: Maxwell, *Treatise* (1873) and Proc. R. Soc. 20 (1872, receding images); Pólya and Szegő, *Isoperimetric Inequalities* (1951); Beckmann, Econometrica 20 (1952); Hashin and Shtrikman, J. Appl. Phys. 33 (1962); Prager and Synge, Q. Appl. Math. 5 (1947); Penfield, Spence and Duinker, *Tellegen's Theorem* (1970); Rumsey, Phys. Rev. 94 (1954); Bendsøe and Sigmund (2003); Ammari and Kang (2007).
- Hartmann, Müsing and Kolar, J. Power Electron. 2009 ([record](https://graz.elsevierpure.com/de/publications/switching-transient-shaping-by-application-of-a-magnetically-coup)) [S]

See also: [README](README.md) · [cross-workstream-synthesis](cross-workstream-synthesis.md) · [research-gaps](research-gaps.md) · [lens-ct](lens-ct.md) · [lens-sy](lens-sy.md) · [lens-ls](lens-ls.md) · [lens-th](lens-th.md)
