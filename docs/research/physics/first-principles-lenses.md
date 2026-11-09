# First-principles lenses: variational, topology, symmetry, length scales, thermodynamics, information, conductor passports

**Status:** partial (seven analyses computed on synthetic cases; principles held where checked; red team corrected several claims; nothing measured or built into the tools).
**First published:** 2026-10-22, commits [ea58675](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ea58675830823f9eea6e143ee616519a34fc76cf) (scripts), [fb92056](https://github.com/magnetic-trowel/kicad-auto-everything/commit/fb92056de1d7ba7caaa43e9733e3ca3b8f022730), [2e32bae](https://github.com/magnetic-trowel/kicad-auto-everything/commit/2e32baee832a0fd98b5f96dd678d27697a8aefa7), [572b899](https://github.com/magnetic-trowel/kicad-auto-everything/commit/572b899c95ecd539b029546d45479ac37642c4cf), [4da7c88](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4da7c88f10744450251cfbb510f63e756b65795f), [e7920b3](https://github.com/magnetic-trowel/kicad-auto-everything/commit/e7920b3482787ac15ad0cfdd1383f18b496e891d) on branch `claude/vigilant-mayer-i91rrr`.

Scope: seven lenses, each re-deriving layout physics from one family of first principles into optimizer objects (certified floors, exact cut prices, image laws, regime lengths, damping ledger, value of information, per-piece conductor passports). Mechanism per lens; derivations in the lens topic docs. Several lenses reached the same results independently (cut law four times): evidence of correctness, not novelty (red team). **Model against model, quasi-static, uncalibrated.** Ideas: [lens-vp](../../ideas/physics-first/lens-vp.md), [lens-ct](../../ideas/physics-first/lens-ct.md), [lens-sy](../../ideas/physics-first/lens-sy.md), [lens-ls](../../ideas/physics-first/lens-ls.md), [lens-th](../../ideas/physics-first/lens-th.md), [lens-in](../../ideas/physics-first/lens-in.md), [lens-cd](../../ideas/physics-first/lens-cd.md).
Keys: lens VP, CT, SY, LS, TH, IN, CD, Thomson, Dirichlet, Beckmann floor, SIMP p = 1, Prager–Synge, polarization tensor, ℓ50, ℓ_m, cut-flux law, ln sec, block–cut theorem, board–world cut I_CM, loop vs node mutual, complex images, wire medium ω_p, modal Q ledger, Q_cu, tuned snubber, Den Hartog, electro-thermal stability, VOI, nugget, Tellegen attribution, Sherman–Morrison, LODF, leverage, cancellation index χ

## Idea and how it works

**VP, variational principles** ([lens-vp](../../topics/physics/lens-vp.md)).
- Self quantities are energy minima over fields the copper constrains: Thomson → upper bounds on R from any trial current; Dirichlet → lower bounds from any trial potential.
- Objective classes: A self energy copper lowers (R, loop L, thermal R; jointly convex in relaxed density ρ); A′ self energy copper raises; B interactions (non-convex, one adjoint each); C EMI masks.
- Beckmann floor P ≥ R_s·W1²/A (W1 = earth-mover distance); convex variable-thickness relaxation (SIMP p = 1) with fractional-knapsack dual certificate; Prager–Synge brackets from potential + stream-function FEM.
- Via spreading L = (μ0d/2π)·ln(R/cap), cap = logarithmic capacity of the via set. Edit price ΔP = R_s·KᵀM(B)K by polarization tensor (disc M = 2·area, slit across flow πℓ²/4).
- R–L crossover = spectrum of R·v = λ·L·v: a thin sheet relaxes wavenumber k at λ(k) = 2R_s|k|/μ0, so half the return lies within ℓ50 ≈ R_s/(2πμ0f).

**CT, conservation and topology** ([lens-ct](../../topics/physics/lens-ct.md)).
- Kirchhoff's laws = exact metric-free half of Maxwell: split each question into an exact topological part (cycles, cuts, articulation points) and a metric part.
- Cut-flux law: crack of length 2a across sheet current costs (π/4)·R_s·Δψ² (Δψ = intercepted current); in a strip ΔR = (2/π)·R_s·ln sec(πx/2), edge notch twice that; exact finite cut = Woodbury rank-k update whose first Neumann term is the plain adjoint.
- Board–world cut: I_CM = −jω·ΣC_i,ext·V_i.
- Block–cut theorem: a region hanging on an articulation point carries zero foreign current; a neck of width w leaks ∝ w² on a flank, ∝ w⁴ at the stagnation point.

**SY, symmetry, reciprocity, duality** ([lens-sy](../../topics/physics/lens-sy.md)).
- Over a plane: loop mutual L′ = μ0·h_a·h_v/(πD²) (independent of width); node mutual C′ ≈ ε0·w_a·w_v/(πD²) (nearly independent of h). So prepreg thickness is a lever on loops only; coplanar guards over thin dielectric do almost nothing.
- Slit law by images; dual needle along the flow; cross-objective crack price ΔJ = (π/4)R_s·Δψ_u·Δψ_λ. Mode conversion V_cm = Δχ·V_dm at changes of imbalance.

**LS, length scales** ([lens-ls](../../topics/physics/lens-ls.md)).
- Circuit valid inside a window bounded by θ = ωℓ/v, Z/Z0, ℓ_m/ℓ, ωτ_e.
- Thin sheet reflects wavenumber k with Γ = 1/(1 + kp), p = 2R_s/(jωμ0): patterns larger than ℓ_m = R_s/(πμ0f) = δ²/t are mirrored (124 mm at 1 kHz, 0.124 mm at 1 MHz, 1 oz). Perfect image → 4–6 complex images (contour-rotated Gauss–Laguerre).
- Decaps + stitching = one wire medium: ∇²V = γ²V, ω² = ω_p² + v²k², ω_p² = n/(L_post·C′).
- Non-perturbative trigger: ε·Q ≥ 1 → switch to co-simulation.

**TH, thermodynamics and dissipation** ([lens-th](../../topics/physics/lens-th.md)).
- Modal Q ledger 1/Q_m = Σ_k 1/Q_mk; wide copper's own Q_cu = h/max(δ, δ²/t).
- Tuned snubber (Den Hartog absorber): branch resistive when L_s·C_s = L·C_oss, so the snubber's mounting inductance is a tuning variable.
- Self-damping plane cavities 1/Q = tanδ + δ/d; edge RC terminations at R_m = η0·d/(√εr·p).
- Fluctuation–dissipation S_v = 4kT·Re Z. Electro-thermal stability: stable iff g = ρ(D^½ΘD^½) < 1.

**IN, information and decisions** ([lens-in](../../topics/physics/lens-in.md)).
- Quantities carry beliefs; choose compute, ask, measure or robustify by value of information. Escalate iff margin < zσ, z = Φ⁻¹(1 − c/L).
- Decisions are differential: common bias cancels, P(correct pair) = Φ(|Δ|/(√2·σ_u)), σ_u measured among contenders. Evaluators lose decision quality once candidate spread falls below their "nugget".

**CD, conductor passports** ([lens-cd](../../topics/physics/lens-cd.md)). Per piece of copper:

| Passport entry | Formula |
|---|---|
| current share per source | i_b = Σ S_bp I_p |
| Tellegen attribution | Z_qp = Σ_b ½(v_b^p i_b^q + v_b^q i_b^p) |
| exact removal (Sherman–Morrison; power-grid LODF) | ΔZ_qp = s_b^p·s_b^q / y_bb |
| Thevenin addition | −ΔV^p ΔV^q/(z + Z_th) |
| leverage (spanning-tree probability, Σρ = n − c) | ρ_b = 1 − z_b·y_bb |
| removal cost | attribution/(1 − ρ) |
| cancellation index (per-piece blame must be counterfactual when small) | χ = abs(Σa)/Σabs(a) |

Jobs are signs of exact counterfactuals.

Test cases: one script set per lens on synthetic geometries (strips, pours, a 24 × 14 mm test pour, a 26 × 18 mm 2-layer prototype board with a buck cell, ADC trace and slotted plane, 600 random hot loops), with grid-convergence options. Lens IN's EMI VOI study: Monte Carlo, 200k samples over seven priors.

## Results

All [C], model against model; numbers live in the lens docs (derivation sections linked), corrections in [redteam-corrections](redteam-corrections.md#results) and scopes in [verification-and-limits](../../topics/physics/verification-and-limits.md#1-claims-verified-by-an-independent-method).

| Lens | Headline result | Red-team status |
|---|---|---|
| VP | test-pour floors bracket SIMP and the human trunk; polarization prices edits the area estimate misses ([D1, D4](../../topics/physics/lens-vp.md#3-derivations)) | floors grid-dependent; "avoidable loss" holds only on the 0.1 mm raster; "1.3% outside" corrected to 18–27% |
| CT | strip ln sec law and exact notch factor 2; slot priced by crack form where the plain adjoint is ~30× low ([D1–D3](../../topics/physics/lens-ct.md#3-five-derivations), [solver-ladder](../../topics/physics/solver-ladder.md#6-caching-and-incremental-re-extraction)) | cut law confirmed to 6 digits by Galerkin; ×2 is a square-grid property; world identity needs world-referenced V |
| SY | loop mutual ∝ h², node mutual nearly h-free; cross-objective crack price ([D1, D3](../../topics/physics/lens-sy.md#2-three-derivations)) | "1 oz mirrors a 5 mm loop above 12 kHz" **wrong**: half-mirroring needs ~93 kHz |
| LS | 4–6 complex images replace the perfect image; wire medium matches lumped anti-resonance ([§3, §4](../../topics/physics/lens-ls.md#3-derivation-b-the-plane-as-a-spatial-filter)) | wire medium confirmed by identity; reach uncertain with the via model; "transitions" move up to 10× with the observable |
| TH | Q_cu = h/δ; tuned snubber gives textbook Q at a third of the loss ([D1, D3](../../topics/physics/lens-th.md#2-derivation-map-then-derivations)) | "copper never damps" **wrong** for plane pairs below ~30 MHz; "damping is a 20–27 dB lever" overstated: 12.5–15 dB (Q 10→1) |
| IN | MS2 pick-best predicted from contender spread; nuggets; EMI VOI dominated by off-board offset under its prior ([D2, §3, §5](../../topics/physics/lens-in.md#2-derivations)) | +64% winner drift was a reference artefact (+2.9 → +6.5%); off-board VOI share 10–49% under other priors |
| CD | exact passports for 4,415 pieces in ~25 s; slot bridge and via-site rankings; χ ≪ 1 for couplings ([§4](../../topics/physics/lens-cd.md#4-prototype-a-buck-cell-a-sensitive-trace-and-a-slotted-plane)) | rank-1 vs brute force is "algebra, not physics"; ε_r = 1 overstates world-charge shares up to ~4× |

## Verdict

- Produced exact, cheap tools for self terms (floors, cut prices, passports); showed where first-order adjoints fail (slots, [solver-ladder](../../topics/physics/solver-ladder.md#6-caching-and-incremental-re-extraction)). No floors for couplings or EMI masks; nothing grid-converged or calibrated.
- Descendants: physics core v2 kernels ([physics-ir-and-core](physics-ir-and-core.md)), real-board passports ([physics-critics-and-passports](physics-critics-and-passports.md)). No `kae/src` module imports a lens script; the thermal fin kernel in `kae/src/kae/physics/kernels.py` shares the idea, not code.
- Open per lens: thin-sheet RL solver for slotted/finite planes (LS); periodic adjoints for switching victims (SY); belief ledger (IN); transient passports for ESD/surge (CD); bench tests of tuned snubbers and laminates (TH).

## Code

`tools/research/physics/`, print-only, synthetic inputs, numpy/scipy:
- VP: `vp_floors.py`, `vp_rl_band.py`, `vp_edit_pricing.py`
- CT: `ct_cut_topology.py` (`[strip|pour|neck|closure|nest|cm|all]`)
- SY: `sy_duality_balance.py` (`--converge`), `sy_images_symmetry.py`
- LS: `ls_thin_sheet.py`, `ls_post_lattice.py`, `ls_regime_map.py` (synthetic "RB4" board, not a real one)
- TH: `th_damping_ledger.py`, `th_dissipation_noise.py`, `th_electrothermal.py`
- IN: `in_decision_quality.py`, `in_emi_voi.py`
- CD: `cd_conductor_passport.py` (~2 min, ~1 GB)

Related: [rule-genealogy](rule-genealogy.md) (foundations draw T2–T13 from these lenses), [domain-models](domain-models.md), [validation-program](validation-program.md).
