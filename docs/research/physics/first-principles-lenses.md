# First-principles lenses: variational, topology, symmetry, length scales, thermodynamics, information, conductor passports

**Status:** partial (seven analyses computed on synthetic cases; principles held where checked; red team corrected several claims; nothing measured or built into the tools).
**First published:** 2026-10-22, commits [ea58675](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ea58675830823f9eea6e143ee616519a34fc76cf) (scripts), [fb92056](https://github.com/magnetic-trowel/kicad-auto-everything/commit/fb92056de1d7ba7caaa43e9733e3ca3b8f022730), [2e32bae](https://github.com/magnetic-trowel/kicad-auto-everything/commit/2e32baee832a0fd98b5f96dd678d27697a8aefa7), [572b899](https://github.com/magnetic-trowel/kicad-auto-everything/commit/572b899c95ecd539b029546d45479ac37642c4cf), [4da7c88](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4da7c88f10744450251cfbb510f63e756b65795f), [e7920b3](https://github.com/magnetic-trowel/kicad-auto-everything/commit/e7920b3482787ac15ad0cfdd1383f18b496e891d) on branch `claude/vigilant-mayer-i91rrr`.

Seven "lenses" each re-derived layout physics from one family of first principles and turned it into objects an optimizer could use: certified floors, exact cut prices, image laws, regime lengths, a damping ledger, value of information, and per-piece conductor passports. Several lenses reached the same results independently (the cut law four times), which the red team reads as evidence of correctness, not novelty. **Everything is model against model, quasi-static and uncalibrated.**

## Idea and how it works

**VP, variational principles** ([lens-vp](../../topics/physics/lens-vp.md)). Self quantities layout controls are energy minima over fields the copper constrains. Thomson gives upper bounds on R from any trial current, Dirichlet lower bounds from any trial potential. Objectives are classed A (self energy copper lowers: R, loop L, thermal R; jointly convex in a relaxed density ρ), A′ (self energy copper raises), B (interactions, non-convex, one adjoint each), C (EMI masks). Derivations: Beckmann floor P ≥ R_s·W1²/A with W1 the earth-mover distance; convex variable-thickness relaxation (SIMP p = 1) with a fractional-knapsack dual certificate; Prager–Synge brackets from potential + stream-function FEM; via spreading L = (μ0d/2π)·ln(R/cap) with logarithmic capacity of the via set; edit price ΔP = R_s·KᵀM(B)K by polarization tensor (disc M = 2·area, slit across flow πℓ²/4); the R–L crossover as the spectrum of R·v = λ·L·v, a thin sheet relaxing wavenumber k at λ(k) = 2R_s|k|/μ0, so half the return lies within ℓ50 ≈ R_s/(2πμ0f).

**CT, conservation and topology** ([lens-ct](../../topics/physics/lens-ct.md)). Kirchhoff's laws are the exact metric-free half of Maxwell, so questions split into an exact topological part (cycles, cuts, articulation points) and a metric part. Cut-flux law: a crack of length 2a across sheet current costs (π/4)·R_s·Δψ² (Δψ = intercepted current); in a strip ΔR = (2/π)·R_s·ln sec(πx/2), an edge notch twice that; the exact finite cut is a Woodbury rank-k update whose first Neumann term is the plain adjoint. Board–world cut: I_CM = −jω·ΣC_i,ext·V_i. Block–cut theorem: a region hanging on an articulation point carries zero foreign current; a neck of width w leaks ∝ w² on a flank but ∝ w⁴ at the stagnation point.

**SY, symmetry, reciprocity, duality** ([lens-sy](../../topics/physics/lens-sy.md)). Over a plane, loop mutual L′ = μ0·h_a·h_v/(πD²) (independent of width) while node mutual C′ ≈ ε0·w_a·w_v/(πD²) (nearly independent of h), so prepreg thickness is a lever on loops only and coplanar guards over thin dielectric do almost nothing. Slit law by images; the dual needle along the flow; a cross-objective crack price ΔJ = (π/4)R_s·Δψ_u·Δψ_λ. Mode conversion V_cm = Δχ·V_dm at changes of imbalance.

**LS, length scales** ([lens-ls](../../topics/physics/lens-ls.md)). A circuit is valid inside a window bounded by θ = ωℓ/v, Z/Z0, ℓ_m/ℓ and ωτ_e. A thin sheet reflects wavenumber k with Γ = 1/(1 + kp), p = 2R_s/(jωμ0), so patterns larger than ℓ_m = R_s/(πμ0f) = δ²/t are mirrored (124 mm at 1 kHz, 0.124 mm at 1 MHz, 1 oz). The perfect image is replaced by 4–6 complex images (contour-rotated Gauss–Laguerre). Decaps and stitching are one wire medium: ∇²V = γ²V, ω² = ω_p² + v²k², ω_p² = n/(L_post·C′). Non-perturbative trigger: when ε·Q ≥ 1 switch to co-simulation.

**TH, thermodynamics and dissipation** ([lens-th](../../topics/physics/lens-th.md)). Modal Q ledger 1/Q_m = Σ_k 1/Q_mk; wide copper's own Q is Q_cu = h/max(δ, δ²/t). Tuned snubber (Den Hartog absorber): the branch is resistive when L_s·C_s = L·C_oss, so the snubber's mounting inductance becomes a tuning variable. Self-damping plane cavities, 1/Q = tanδ + δ/d, and edge RC terminations at R_m = η0·d/(√εr·p). Fluctuation–dissipation S_v = 4kT·Re Z. Electro-thermal stability: stable iff g = ρ(D^½ΘD^½) < 1.

**IN, information and decisions** ([lens-in](../../topics/physics/lens-in.md)). Quantities carry beliefs; the system chooses to compute, ask, measure or robustify by value of information. Escalate iff margin < zσ with z = Φ⁻¹(1 − c/L). Decisions are differential: common bias cancels, so P(correct pair) = Φ(|Δ|/(√2·σ_u)) with σ_u measured among contenders. Evaluators lose decision quality once candidate spread falls below their "nugget".

**CD, conductor passports** ([lens-cd](../../topics/physics/lens-cd.md)). Every piece of copper gets a passport: current share per source (i_b = Σ S_bp I_p), Tellegen attribution Z_qp = Σ_b ½(v_b^p i_b^q + v_b^q i_b^p), exact removal ΔZ_qp = s_b^p·s_b^q / y_bb (Sherman–Morrison; the power-grid LODF), Thevenin addition −ΔV^p ΔV^q/(z + Z_th), leverage ρ_b = 1 − z_b·y_bb (spanning-tree probability, Σρ = n − c), removal cost = attribution/(1 − ρ). Jobs are signs of exact counterfactuals. The cancellation index χ = |Σa|/Σ|a| shows when per-piece blame must be counterfactual.

## What we tried

One script set per lens on synthetic geometries (strips, pours, a 24 × 14 mm test pour, a 26 × 18 mm 2-layer prototype board with a buck cell, ADC trace and slotted plane, 600 random hot loops), with grid-convergence options. Lens IN's EMI value-of-information study used Monte Carlo with 200k samples over seven priors.

## Results

All [C]. Sources: the lens topic docs above and [verification-and-limits](../../topics/physics/verification-and-limits.md).

| Lens | Key computed result | Red-team status |
|---|---|---|
| VP | test pour: Beckmann ≥ 1.527 mΩ, convex ≥ 1.761, SIMP 1.789, human trunk 2.092 mΩ; edit pricing on 16 edits: area estimate 0.03–0.88× exact, polarization 0.78–0.89× | floors move 2.2–12.8% between 0.2 and 0.1 mm grids, two grids used different areas: "14.5–15.8% avoidable" holds only on the 0.1 mm raster; band "1.3% outside" corrected to 18–27% |
| CT | strip ln sec forms within 0.15% (x = 0.1–0.9), notch/slit = 2.000; 6 mm slot: exact +8.06 mW, plain adjoint 0.27 mW (29× low), Δψ² law 6.40 mW; neck leakage flank vs stagnation ~1,300× | cut law confirmed to 6 digits by Galerkin; ×2 is a square-grid property; world identity needs world-referenced V |
| SY | L_m′ ∝ h^1.98, C_m′ ∝ h^0.19 (2 mm strips); grounded guard −1–3% at h 0.1 mm, −48% at 1.6 mm; cross-objective price within 3–12% of FD where plain adjoint was 13–35× low | "1 oz mirrors a 5 mm loop above 12 kHz" **wrong**: half-mirroring needs ~93 kHz |
| LS | complex images: worst L′ error 68% (perfect image) → 0.8%/3.5% (4 images) → 0.5%/0.4% (6); wire medium anti-resonance 1898 vs 1898 MHz | wire medium confirmed by identity; via-model spread 2–6× gives 1.4–2.4× in reach; "transitions" move up to 10× with the observable |
| TH | Q_cu within 0.93–1.30 of a two-slab model; tuned snubber Q 1.01 at 72 mW vs textbook 0.96 at 216 mW (12 V, 500 kHz, C_oss 1 nF) but Q 2.72 over C_oss 0.5–2× | "copper never damps" **wrong** for plane pairs below ~30 MHz; "damping is a 20–27 dB lever" overstated: 12.5–15 dB (Q 10→1) |
| IN | MS2 96.3% pick-best observed vs 97.0/93.9% predicted, area 15.8%; MS2 on a 0.5 mm grid drops to 47.6% (nugget); EMI EVPI 15.2, 84% from enclosure/cable offset | +64% winner drift was a reference artefact (+2.9 → +6.5%); off-board VOI share 10–49% under other priors |
| CD | 4,415 pieces × 4 bands × 10 budgets in ~25 s; 62% of the ADC's 1.47 mV DC error in two plane regions; one 0.5 mm slot bridge removes 78% of HF coupling; best of 203 via sites −35.5 pH (median −0.03); χ = 0.08–0.10 | rank-1 vs brute force 2×10⁻⁹ is "algebra, not physics"; ε_r = 1 overstates world-charge shares up to ~4× |

## Verdict

The lenses produced exact, cheap tools for self terms (floors, cut prices, passports) and showed where first-order adjoints fail by 30×. They did not produce floors for couplings or EMI masks, and nothing is grid-converged or calibrated. Their concrete descendants are physics core v2's kernels ([physics-ir-and-core](physics-ir-and-core.md)) and the real-board passports ([physics-critics-and-passports](physics-critics-and-passports.md)). No `kae/src` module imports a lens script; the thermal fin kernel in `kae/src/kae/physics/kernels.py` shares the idea, not code. Open per lens: thin-sheet RL solver for slotted/finite planes (LS), periodic adjoints for switching victims (SY), a belief ledger (IN), transient passports for ESD/surge (CD), bench tests of tuned snubbers and laminates (TH).

## Code

`tools/research/physics/`, print-only, synthetic inputs, numpy/scipy:
- VP: `vp_floors.py`, `vp_rl_band.py`, `vp_edit_pricing.py`
- CT: `ct_cut_topology.py` (`[strip|pour|neck|closure|nest|cm|all]`)
- SY: `sy_duality_balance.py` (`--converge`), `sy_images_symmetry.py`
- LS: `ls_thin_sheet.py`, `ls_post_lattice.py`, `ls_regime_map.py` (synthetic "RB4" board, not a real one)
- TH: `th_damping_ledger.py`, `th_dissipation_noise.py`, `th_electrothermal.py`
- IN: `in_decision_quality.py`, `in_emi_voi.py`
- CD: `cd_conductor_passport.py` (~2 min, ~1 GB)

Ideas: [lens-vp](../../ideas/physics-first/lens-vp.md), [lens-ct](../../ideas/physics-first/lens-ct.md), [lens-sy](../../ideas/physics-first/lens-sy.md), [lens-ls](../../ideas/physics-first/lens-ls.md), [lens-th](../../ideas/physics-first/lens-th.md), [lens-in](../../ideas/physics-first/lens-in.md), [lens-cd](../../ideas/physics-first/lens-cd.md).

## Related

[rule-genealogy](rule-genealogy.md) (foundations draw T2–T13 from these lenses), [redteam-corrections](redteam-corrections.md), [domain-models](domain-models.md), [validation-program](validation-program.md).
