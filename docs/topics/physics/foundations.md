# Foundations: physics gently applied to circuits

Scope: the circuit as zeroth-order Maxwell, gentleness criterion G, seven principles F1–F7, theorems T1–T13, what a conductor is doing. Not here: derivations and the 26-rule trace -> [foundations-derivations](foundations-derivations.md); symbols -> [vocabulary](vocabulary.md#glossary).
Keys: zeroth order, gentleness, loop gain G, spectral radius, convergence radius, first principles F1-F7, theorems T1-T13, impedance level, exactness ladder, invisible/known/designed, netlist quotient, passport

[C] = uncalibrated, by [fd_gentleness.py](../../../tools/research/physics/fd_gentleness.py) or [fd_impedance_level.py](../../../tools/research/physics/fd_impedance_level.py). Idea ids: [catalog](../../ideas/physics-first/README.md).

## The circuit is the zeroth order

Maxwell = exact metric-free half (charge conservation, Faraday per cycle; [lens-ct](lens-ct.md)) + approximate half (ε, μ, σ, geometry). A schematic keeps the first and lumps the second into parts. Valid while these are small ([lens-ls](lens-ls.md)):

| Edge | Small parameter | Board example |
|---|---|---|
| Size | θ = ωℓ/v | 10 mm at 100 MHz: 0.04 |
| Series (KVL) | ε_L = θ·Z0/Z | 1 at 160 kHz (1 mΩ shunt, 1 nH) |
| Shunt (KCL) | ε_C = θ·Z/Z0 | 1 at 8 MHz (100 kΩ, 0.2 pF) |
| Conductor | R/\|Z\|; ℓ_m/ℓ, ℓ_m = R_s/(πμ0f) = δ²/t | ℓ_m 124 mm at 1 kHz, 0.12 mm at 1 MHz (1 oz) |
| Insulator | 1/(ωτ_e) | humid residue, τ_e ≈ 23 µs |
| Heat | g = ρ(D^½ΘD^½) | 0.16–0.54 on 1–3 W boards ([lens-th](lens-th.md)) |

Window: η0/R_s ≈ 7.7×10⁵ (1 oz). Geometry offers Z0 only from tens of mΩ to ~170 Ω; circuits span mΩ to GΩ.

**Gentleness criterion G.** Eliminating a hidden coordinate (mode, reflection, eddy, temperature, an edit's own redistribution) gives the circuit (I − G)⁻¹ = Σ Gⁿ. "Circuit + parasitics", back-annotation, adjoint prices and one-pass electro-thermal stop at n = 1: valid iff spectral radius ρ(G) < 1 (no natural mode inside the expansion disc); error ≈ first neglected term. Radii (mode ε < 1/Q with error (εQ)², line θ < ln|(m+1)/(m−1)|, edit λ_max < 1, heat g < 1, plane eddies kℓ_m ≠ 1) and checks [C]: [D1](foundations-derivations.md#d1-the-gentleness-criterion-g).

Beyond the radius: promote the coordinate into the circuit (line, mode, complex images, fixed point: LS15, VP18, LS1, TH29). A precision victim needs more orders, n* ≈ ln(B/S)/ln ε (LS13), not more fidelity. Two moves keep a layout gentle: **match** (Z0 = Z removes the mode, T1), **damp** (Q → 1 moves it off the band, T10).

**Thesis.** The designer chooses the domain inside the fab's feasible set; nature minimizes field energy inside it ([lens-vp](lens-vp.md)). Keep each part of the realization **invisible** (inside the radius and small), **known** (inside it, budgeted with σ) or **designed** (promoted into the circuit with a spec: line, damper, shunt, antenna).

Make G a core service: every evaluator reports its loop gains (εQ, λ_max, g, line radius) and order; beyond the radius promote the coordinate rather than escalate fidelity (LS15, VP18, CD6) [I].

## Seven first principles

| # | Principle | Equation | Valid where |
|---|---|---|---|
| F1 | **Conservation and topology** | ∇·(J + ∂D/∂t) = 0; ∮_γE·dl = −dΦ_γ/dt; ∇·B = 0. On any graph: KCL, KVL, Tellegen Σv_k·i_k = 0 | Exact and metric-free, nonlinear parts included, once displacement edges and a world node are added. Only cycle sums are physical (gauge) |
| F2 | **Linear, passive, reciprocal, causal media** (where all model error lives) | D = εE, B = μH, J = σE, symmetric positive tensors: superposition per band, Z = Zᵀ, Re Z ≥ 0, Kramers–Kronig | Copper, laminate, air. Breaks at TCR, breakdown, ferrite saturation, piezo MLCCs, advection (airflow: "electrolytics upstream"); parts carry nonlinearity and switching (periodic adjoints, SY2) |
| F3 | **Extremum principles** | I²R = min ∫R_s\|K\|² (Thomson); ½LI² = min ½IᵀL_pI (ωL ≫ R); CV² = min ∫ε\|∇φ\|²; dual forms bracket | From F1 + F2. A minimum (monotone, convex, certified) only in pure R, L or C regimes, for self terms; the RL band is only stationary (Rumsey); AC resistance can rise with copper |
| F4 | **Symmetry and duality** | Images (PEC/PMC signs); even/odd parity; sheet duality φ/R_s ↔ ψ (cut ↔ needle); Babinet; wedge fields ∝ r^(π/α−1) | Images: patterns larger than ℓ_m, a few h from edges, below cavity modes. Duality: 2-D sheets, thin screens |
| F5 | **Locality, scale and causality** | Sheets: ∇²u = γ²u, complex γ² (screen, diffuse, propagate), plus the non-local \|k\| magnetic kernel; delay ≥ ℓ/v; homogenize when pitch ≪ field length | Thin sheets; quasi-TEM; scales in [lens-ls](lens-ls.md) |
| F6 | **Dissipation and fluctuation** | 1/Q_m = Σ_k 1/Q_mk; S_v = 4kT·Re Z; G_th = L·T·G_el (metal), G_th/C = k/ε (dielectric); damage Σ∫ḋ·dt ≤ 1 | Linear modes; local equilibrium; damage rates empirical [S] |
| F7 | **Decisions under belief** | VOI ≥ 0, zero if no outcome changes the action; rankings use differences (bias cancels), verdicts need \|bias + spread\| ≪ margin; Var y ≈ Σ s_j²σ_j² | Decision theory; values depend on priors and costs ([lens-in](lens-in.md)) |

F1, F2 = Maxwell's two halves (Tonti [S]); F3–F5 = the structure they give a board; F6 = second law; F7 = epistemics.

## Theorem T1: impedance level

**T1.** A uniform go/return piece, delay T = ℓ/v, characteristic impedance Z0, swings ΔV and ΔI in one band between equal real terminations Z; m = Z0/Z.
1. **Energy.** Stores ½T(Z0·ΔI² + ΔV²/Z0) ≥ T·ΔV·ΔI; equality iff Z0 = ΔV/ΔI.
2. **Order.** First-order effect is a pure phase θ(m + 1/m)/2 ≥ θ; amplitude error is second order, −(θ²/8)(m − 1/m)². At m = 1: exact delay exp(−jθ) at any length.
3. **Damping.** Q = 1 at R = Z0.

Conditions: self terms only; quasi-TEM; ΔV/ΔI per piece and per band. Derivation, limits and checks [C] (interactions overrule it: buck SW dipole 7.5×; Bode–Fano; matching is local; one-sided for shunt structures; residual delay ∝ length): [D2](foundations-derivations.md#d2-impedance-level-t1).

Classify pieces per band by ΔV/ΔI against Z0 (LS5); synthesize dampers (R ≈ Z0 at antinodes) wherever εQ ≥ 1 (TH1–TH4).

## Design theorems: the derivation tree

Principle → theorem [conditions] → results explained. [Rule-of-thumb trace](foundations-derivations.md#r-rule-of-thumb-trace) runs the tree backward from 26 rules.

| Id | Theorem | From | Explains |
|---|---|---|---|
| T1 | **Impedance level.** Length sets θ, shape sets Z0; drive Z0 toward ΔV/ΔI; damp with R = Z0 [self terms; quasi-TEM] | F3, F5 | PW2, LA36, LS5–LS7, XD19, FE31 |
| T2 | **Copper localizes or damps, never both [I].** Q_cu = h/max(δ, δ²/t): ½ at f_x, h/δ (30–170 for hot-loop rings) above the skin frequency [C] [w ≫ h] | F3, F5, F6 | f_x "found four times"; gap 2; star vs plane; TH D1 |
| T3 | **Self vs interaction.** Z_pq = ¼[Z(s_p+s_q) − Z(s_p−s_q)]: sign-indefinite, unprotected by Rayleigh, attributions cancel [reciprocal band] | F2, F3 | VP classes A/B/C, CD D2 (χ 0.08), XD122, LA45 |
| T4 | **Exact edit pricing.** ΔJ = vᵀ(D⁻¹ − UᵀK⁻¹U)⁻¹v, first order × 1/(1 − ρ) per piece; slits → (π/4)R_s·Δψ_u·Δψ_λ [linear band; between topological events] | F1, F2, G | slot miss ([solver-ladder](solver-ladder.md#6-caching-and-incremental-re-extraction)), hand-set 2×, S1, SIM24–25, XD51 |
| T5 | **Budgets live on closed cycles.** Two-point AC voltages depend on path; partial-L shares are a gauge; Kelvin = the sense cycle carries none of the load's drop [AC] | F1 | FE1, LA21, CT22, SY22, CD34 |
| T6 | **The world is a node.** I_CM = −jω·Σ C_i,ext·V_i; a bond moves a displacement edge inside the boundary [cables, chassis, heatsink] | F1, F7 | S4, DR28, CT9, CT16; off-board unknowns dominate VOI under one prior, 10–49% under others (IN6, [lens-in §5](lens-in.md#5-the-measurement-program-as-experiment-design)) |
| T7 | **Topology is exact and discrete.** Articulation points pass zero foreign current; necks leak ∝ w² on a flank, ∝ w⁴ at a stagnation point; cycle rank is a per-band choice; vias, cuts and joins are events [per-band conduction graph] | F1 | DR26, RG19, CT18–CT20, CT28, JPR2 |
| T8 | **Planes are band-limited mirrors.** Image patterns larger than ℓ_m (4–6 complex images within 0.5–3.5%); decaps and stitching vias form one wire medium, ω² = ω_p² + v²k² [thin, intact planes] | F4, F5 | XD113, FE26–FE29, PW37, LS1, LS8 |
| T9 | **Symmetry residuals.** Conversion happens where χ changes (Bal ≡ Vcm); mirrored halves give null planes, not smaller halos; gentle loops are current-forced and nodes voltage-forced, so a plane shrinks a loop's moment (∝ h), not a wide node's (2ε∫V·dA) [I] | F4, G | FE35, S5, SY D1, PW14 |
| T10 | **Designed dissipation.** A mode with excitation × Q over budget needs a tuned loss channel at its antinode (R ≈ Z0; L_s·C_s ≈ L·C_oss); stitching moves modes but keeps Q; dampers add noise and heat [linear modes] | G, F6, T1 | TH1–TH12, PDN-10, FE31; tuned snubber 72 vs 216 mW |
| T11 | **Loss vs damage.** Loss is an L2 norm, finite at any corner; damage is local, high-order, sees r^(π/α−1) [pulses shorter than w²/κ, κ copper diffusivity; HV; fusing] | F3, F4, F6 | PW18, SY26, TH33 |
| T12 | **Exactness ladder.** Topology (exact) → variational floors and brackets (certified) → rank-k counterfactuals (exact in the model) → closed forms (exact in an idealization) → fields (±σ) → measurement | F1–F3 | VP1–VP10, CT27, CD2; fidelity tiers grade accuracy, not guarantees ([solver-ladder](solver-ladder.md)) |
| T13 | **Ranking vs compliance; robustness vs information.** Bias cancels in a ranking (MS2 picks 96%) but not in a verdict (winner drift +6.5%; the +64% was a reference artefact, [lens-in D4](lens-in.md#2-derivations)); cut s_j or σ_j, whichever is cheaper | F7 | SIM7, SIM10, DR33, IN13, IN17 |

Tag terms self, interaction or mask (VP20), and verdicts by exactness rung; rankings never certify compliance (IN13, IN17).

## What a conductor is doing

**Definition.** A piece (strip, via, pad cell, plane region) is doing whatever would change if it changed: its column of exact counterfactuals ΔB_k on every budget k, for removal and extension, per band (T4). Its jobs = the column's signs ([lens-cd](lens-cd.md) P7); "designed" or "parasitic" belongs to a (piece, job) pair. State that explains the column:
1. **Currents** (F2): share of each source's current, transport, induced circulation.
2. **Charges** (F1): share by driven node; where field lines end: own return, victims, world.
3. **Energies** (F3, F6): stored, dissipated, guided (Poynting flux in its gap), radiated.
4. **Topology** (F1): bridge, shared edge, chord, ring, handle, cut member or linked; leverage ρ.
5. **Symmetry and scale** (F4, F5): imbalance χ, image validity, θ, ΔV/ΔI against Z0, ℓ_m/ℓ.
6. **Dissipation** (F6): share of each mode's damping, noise 4kT·R_b·\|H_b→y\|², heat, thermal conductance.
7. **Stress** (F4, F6): edge field, potential to neighbours, ωτ_e, damage rate.
8. **Belief** (F7): value, σ, exactness rung, lineage.

Build the passport (CD1) from these eight rows; world node and off-board conductors mandatory (CT16, IN6).

**Netlist = quotient.** A netlist collapses each connected conductor to a node ([D9](foundations-derivations.md#d9-the-netlist-as-a-quotient-5-of-foundations)): keeps which pins share copper, drops metric, holes and rings that carry circulation, world node and band, where all eight rows live. Two layouts of one netlist differ only in what it drops: an autorouter can be DRC-correct and physically wrong.

## Open questions

G shown on closed forms and toys, not on a whole board. No principle prices self and interaction terms jointly. Nonlinear victims, ESD and surge fall outside F2 (LS32). Every [C] is model against model.

## Sources

- [C]: [fd_gentleness.py](../../../tools/research/physics/fd_gentleness.py), [fd_impedance_level.py](../../../tools/research/physics/fd_impedance_level.py), reusing [th_damping_ledger.py](../../../tools/research/physics/th_damping_ledger.py) and [fe_cavity.py](../../../tools/research/physics/fe_cavity.py).
- [S]: E. Tonti, *The Mathematical Structure of Classical and Relativistic Physics*, 2013; R. M. Fano, J. Franklin Inst. 249, 1950 (Bode–Fano); V. H. Rumsey, Phys. Rev. 94, 1954.

See also: [README](README.md) · [cross-workstream-synthesis](cross-workstream-synthesis.md) · [research-gaps](research-gaps.md) · lenses [VP](lens-vp.md), [CT](lens-ct.md), [SY](lens-sy.md), [LS](lens-ls.md), [TH](lens-th.md), [IN](lens-in.md), [CD](lens-cd.md)
