# Foundations: physics gently applied to circuits

**TL;DR**
- **A circuit is Maxwell at zeroth order, and "gently applied" means a convergent series.** Layout adds hidden coordinates (modes, reflections, eddies, temperature, an edit's own redistribution) that feed back through a loop gain G. Back-annotated parasitics, adjoint prices and one-pass electro-thermal truncate Σ Gⁿ at first order, valid only inside the nearest natural mode, e.g. |δL/L| < 1/Q at a resonance [C]. Beyond it, the coordinate must join the circuit.
- **Seven principles:** conservation and topology (exact); linear, passive, reciprocal media (where all model error lives); extremum principles; symmetry; locality and scale; dissipation and fluctuation; decisions under belief.
- **Candidate principle 5 survives as theorem T1, for self terms only.** A piece swinging ΔV and ΔI stores at least ΔV·ΔI·T, with equality iff Z0 = ΔV/ΔI; matched, it is an exact delay; Q = 1 at R = Z0 is its damping form [C]. But a buck switch node's self-optimal width would multiply its external dipole 7.5×.
- **Thirteen theorems replace round 1's fourteen principles** (5 kept, 9 restated). Interactions are differences of self energies; an exact edit price is the first-order price ÷ (1 − leverage); budgets live on closed cycles; the world is a node; excited modes need designed loss; wide copper localizes its return or damps itself, never both; verdicts climb an exactness ladder.
- **What a conductor is doing** is its per-piece, per-band column of exact counterfactuals on every budget. A netlist collapses each conductor to a point, so it holds only the zeroth order.

Tags: [S] secondary, [I] inference, [C] computed (uncalibrated) by [fd_gentleness.py](../../../tools/research/physics/fd_gentleness.py) or [fd_impedance_level.py](../../../tools/research/physics/fd_impedance_level.py). Derivations and a trace of 26 rules of thumb: [foundations-derivations](foundations-derivations.md). Ids: [catalog](../../ideas/physics-first/README.md).

## Key facts

### 1. The starting point: the circuit is the zeroth order

Maxwell's equations have an exact, metric-free half (charge conservation, Faraday's law per cycle) and an approximate half (ε, μ, σ and the geometry they fill) ([lens-ct](lens-ct.md)). A schematic keeps the first and lumps the second into parts. It stays accurate while these ratios are small; layout is where a structure nears an edge ([lens-ls](lens-ls.md)):

| Edge | Small parameter | Board example |
|---|---|---|
| Size | θ = ωℓ/v | 10 mm at 100 MHz: 0.04 |
| Series (KVL) | ε_L = θ·Z0/Z | 1 at 160 kHz (1 mΩ shunt, 1 nH) |
| Shunt (KCL) | ε_C = θ·Z/Z0 | 1 at 8 MHz (100 kΩ, 0.2 pF) |
| Conductor | R/\|Z\|; ℓ_m/ℓ, ℓ_m = R_s/(πμ0f) = δ²/t | ℓ_m 124 mm at 1 kHz, 0.12 mm at 1 MHz (1 oz) |
| Insulator | 1/(ωτ_e) | humid residue, τ_e ≈ 23 µs |
| Heat | g = ρ(D^½ΘD^½) | 0.16–0.54 on 1–3 W boards ([lens-th](lens-th.md)) |

The window is wide (η0/R_s ≈ 7.7×10⁵ for 1 oz), but geometry offers Z0 only from tens of mΩ to about 170 Ω; circuits span mΩ to GΩ.

**G, the gentleness criterion.** Eliminating a hidden coordinate gives the circuit a factor (I − G)⁻¹ = Σ Gⁿ; "circuit + parasitics" stops at n = 1, which is valid iff the spectral radius of G is below 1 (no natural mode inside the expansion disc), with error about the first neglected term. The radii are ε < 1/Q for a mode (first-order error (εQ)²), θ < ln|(m+1)/(m−1)| for a line (infinite when matched), collective leverage λ_max < 1 for an edit (0.977 for a slit across 92% of a strip: 41× its first-order price), g < 1 for heat, and kℓ_m away from 1 for plane eddies ([D1](foundations-derivations.md#d1-the-gentleness-criterion-g)) [C].

Beyond the radius, promote the coordinate into the circuit: a line, a mode, complex images, a fixed point (LS15, VP18, LS1, TH29). A precision victim needs more orders, n* ≈ ln(B/S)/ln ε (LS13), not more fidelity. Two moves keep a layout gentle: **match** (Z0 = Z removes the mode, T1) and **damp** (Q → 1 moves it off the band, T10).

**Restated thesis.** The designer chooses the domain inside the fab's feasible set; nature minimizes field energy inside it ([lens-vp](lens-vp.md)). Physics-first layout keeps each part of that realization **invisible** (inside the radius and small), **known** (inside it, budgeted with σ) or **designed** (promoted into the circuit with a spec: a line, a damper, a shunt, an antenna).

### 2. Seven first principles

| # | Principle | Equation | Valid where |
|---|---|---|---|
| F1 | **Conservation and topology** | ∇·(J + ∂D/∂t) = 0; ∮_γE·dl = −dΦ_γ/dt; ∇·B = 0. On any graph: KCL, KVL, Tellegen Σv_k·i_k = 0 | Exact and metric-free, nonlinear parts included, once displacement edges and a world node are added. Only cycle sums are physical (gauge) |
| F2 | **Linear, passive, reciprocal, causal media** | D = εE, B = μH, J = σE, symmetric positive tensors: superposition per band, Z = Zᵀ, Re Z ≥ 0, Kramers–Kronig | Copper, laminate, air. Breaks at TCR, breakdown, ferrite saturation, piezo MLCCs, advection (airflow: "electrolytics upstream"); parts carry nonlinearity and switching (periodic adjoints, SY2) |
| F3 | **Extremum principles** | I²R = min ∫R_s\|K\|² (Thomson); ½LI² = min ½IᵀL_pI (ωL ≫ R); CV² = min ∫ε\|∇φ\|²; dual forms bracket | From F1 + F2. A minimum (monotone, convex, certified) only in pure R, L or C regimes, for self terms; the RL band is only stationary (Rumsey), and AC resistance can rise with copper |
| F4 | **Symmetry and duality** | Images (PEC/PMC signs); even/odd parity; sheet duality φ/R_s ↔ ψ (cut ↔ needle); Babinet; wedge fields ∝ r^(π/α−1) | Images: patterns larger than ℓ_m, a few h from edges, below cavity modes. Duality: 2-D sheets, thin screens |
| F5 | **Locality, scale and causality** | Sheets: ∇²u = γ²u, complex γ² (screen, diffuse, propagate), plus the non-local \|k\| magnetic kernel; delay ≥ ℓ/v; homogenize when pitch ≪ field length | Thin sheets; quasi-TEM; scales in [lens-ls](lens-ls.md) §5 |
| F6 | **Dissipation and fluctuation** | 1/Q_m = Σ_k 1/Q_mk; S_v = 4kT·Re Z; G_th = L·T·G_el (metal), G_th/C = k/ε (dielectric); damage Σ∫ḋ·dt ≤ 1 | Linear modes; local equilibrium; damage rates empirical [S] |
| F7 | **Decisions under belief** | VOI ≥ 0, zero if no outcome changes the action; rankings use differences (bias cancels), verdicts need \|bias + spread\| ≪ margin; Var y ≈ Σ s_j²σ_j² | Decision theory; values depend on priors and costs ([lens-in](lens-in.md)) |

F1 and F2 are Maxwell's two halves (Tonti [S]); F3–F5 are the structure they give a board; F6 adds the second law, F7 the epistemics.

### 3. Candidate principle 5, tested

A uniform go/return piece has L = Z0·T and C = T/Z0, so swinging ΔI and ΔV it stores ½T(Z0·ΔI² + ΔV²/Z0) ≥ T·ΔV·ΔI, with equality iff Z0 = ΔV/ΔI. Between real terminations its first-order effect is a phase θ(m + 1/m)/2, and at m = 1 it is an exact delay ([lens-ls](lens-ls.md), [lens-vp](lens-vp.md) D6). Tests ([D2](foundations-derivations.md#d2-impedance-level-t1)) [C]: a 50 Ω line tolerates ±10% in Z0 at ≤ 0.05 dB. In a 12 V, 10 A buck, VIN/GND pieces carry 0.15 Ω (CIN holds VIN), so the widest wins; the switch-node piece carries 1.2 Ω and is self-optimal at 15 mm, but stakes 4 nJ against C_oss's 22 nJ while its external dipole grows 7.5×. A PDN stage (R + jωL) ∥ (R + 1/jωC) equals R at every ω iff √(L/C) = R and stays ≤ R iff √(L/C) ≤ R; cavity peaks equal Q·Z0_mode within 0–8%. A 1 MΩ node sits at m ≈ 10⁻⁴, so only its C matters.

**Verdict: keep it as T1, with limits.** It covers self terms only (the switch node shows the conflict with interactions), with ΔV/ΔI per piece and band. The exact delay needs a real Z; for reactive loads Bode–Fano rules, and no lossless network matches 50 Ω ∥ 1 pF better than \|Γ\| = 0.54 over 0–16 GHz. Matching is local: sections of 100 and 25 Ω give √(L/C) = 50 Ω but L·C = 1.56T². Shunt structures make it one-sided: each mode's Z0 ≤ Z_t, damped by R ≈ Z_t. The residual delay goes only with length.

The damping form is the same theorem: TH's edge resistor η0·d/(√εr·p) is the Z0 of a p-wide strip of the plane pair, and with it no cavity peak remains.

### 4. Design theorems: the derivation tree

Rows run principle → theorem [conditions] → results explained; [§R](foundations-derivations.md#r-rule-of-thumb-trace) runs the tree backward from 26 rules of thumb.

| Id | Theorem | From | Explains |
|---|---|---|---|
| T1 | **Impedance level.** Length sets θ, shape sets Z0; drive Z0 toward ΔV/ΔI; damp with R = Z0 [self terms; quasi-TEM] | F3, F5 | PW2, LA36, LS5–LS7, XD19, FE31 |
| T2 | **Copper localizes or damps, never both [I].** Q_cu = h/max(δ, δ²/t): ½ at f_x, h/δ (30–170 for hot-loop rings) above the skin frequency [C] [w ≫ h] | F3, F5, F6 | f_x "found four times"; gap 2; star vs plane; TH D1 |
| T3 | **Self vs interaction.** Z_pq = ¼[Z(s_p+s_q) − Z(s_p−s_q)]: sign-indefinite, unprotected by Rayleigh, attributions cancel [reciprocal band] | F2, F3 | VP classes A/B/C, CD D2 (χ 0.08), XD122, LA45 |
| T4 | **Exact edit pricing.** ΔJ = vᵀ(D⁻¹ − UᵀK⁻¹U)⁻¹v, first order × 1/(1 − ρ) per piece; slits → (π/4)R_s·Δψ_u·Δψ_λ [linear band; between topological events] | F1, F2, G | 30× slot miss, hand-set 2×, S1, SIM24–25, XD51 |
| T5 | **Budgets live on closed cycles.** Two-point AC voltages depend on path; partial-L shares are a gauge; Kelvin = the sense cycle carries none of the load's drop [AC] | F1 | FE1, LA21, CT22, SY22, CD34 |
| T6 | **The world is a node.** I_CM = −jω·Σ C_i,ext·V_i; a bond moves a displacement edge inside the boundary [cables, chassis, heatsink] | F1, F7 | S4, DR28, CT9, CT16; off-board unknowns hold 33–84% of VOI (IN6) |
| T7 | **Topology is exact and discrete.** Articulation points pass zero foreign current; necks leak ∝ w² on a flank, ∝ w⁴ at a stagnation point; cycle rank is a per-band choice; vias, cuts and joins are events [per-band conduction graph] | F1 | DR26, RG19, CT18–CT20, CT28, JPR2 |
| T8 | **Planes are band-limited mirrors.** They image patterns larger than ℓ_m (4–6 complex images within 0.5–3.5%); decaps and stitching vias form one wire medium, ω² = ω_p² + v²k² [thin, intact planes] | F4, F5 | XD113, FE26–FE29, PW37, LS1, LS8 |
| T9 | **Symmetry residuals.** Conversion happens where χ changes (Bal ≡ Vcm); mirrored halves give null planes, not smaller halos; gentle loops are current-forced and nodes voltage-forced, so a plane shrinks a loop's moment (∝ h), not a wide node's (2ε∫V·dA) [I] | F4, G | FE35, S5, SY D1, PW14 |
| T10 | **Designed dissipation.** A mode with excitation × Q over budget needs a tuned loss channel at its antinode (R ≈ Z0; L_s·C_s ≈ L·C_oss); stitching moves modes but keeps Q; dampers add noise and heat [linear modes] | G, F6, T1 | TH1–TH12, PDN-10, FE31; tuned snubber 72 vs 216 mW |
| T11 | **Loss vs damage.** Loss is an L2 norm, finite at any corner; damage is local and high-order and sees r^(π/α−1) [pulses shorter than w²/κ (κ: copper diffusivity), HV, fusing] | F3, F4, F6 | PW18, SY26, TH33 |
| T12 | **Exactness ladder.** Topology (exact) → variational floors and brackets (certified) → rank-k counterfactuals (exact in the model) → closed forms (exact in an idealization) → fields (±σ) → measurement | F1–F3 | VP1–VP10, CT27, CD2; round-1 F0–F4 graded accuracy, not guarantees |
| T13 | **Ranking vs compliance; robustness vs information.** Bias cancels in a ranking (MS2 picks 96%) but not in a verdict (+64% on winners); cut s_j or σ_j, whichever is cheaper | F7 | SIM7, SIM10, DR33, IN13, IN17 |

### 5. Round 1's fourteen principles

| # | Round 1 ([README](README.md)) | Verdict and new form |
|---|---|---|
| 1 | Ports and loops, not wires | Restate: every current closes by conduction, internal displacement or the world (T5, T6); a port closing only through the world is an antenna (CT15) |
| 2 | Classify copper by waveform | Restate: by ΔV/ΔI per piece and band against Z0 (T1), interactions apart (T3) |
| 3 | Width trades parasitics; length and height win | Restate: length sets θ, shape sets Z0 (T1); height is a lever for current-forced loops only (T9) |
| 4 | One screened-Laplace equation | Restate: one complex-γ² operator plus the \|k\| kernel (F5); decap reach holds only from SRF to f_p (T8) |
| 5 | Shape copper by current flow | Keep, for self terms, now with certified floors and exact edit prices (T4, T12) |
| 6 | Return impedance is the currency | Restate: cycle EMFs with the victim's closure (T5), plus voltage-driven CM (T6) |
| 7 | Topology before tweaks | Keep: topological levers are exact and discrete (T7), metric ones leading-order (F5); robust choices cap VOI (T13) |
| 8 | Geometric detail is regime-gated | Restate: corners matter for damage, not loss (T11) |
| 9 | Budgets from the circuit; least slack first | Restate: on cycles and modes (T5, T10), as P(LII ≤ 1); periodic adjoints for switching victims; τ from certified floors |
| 10 | Placement and routing are one problem | Keep: the outer level of the bilevel problem; topological events stay discrete (T7) |
| 11 | Fidelity follows decisions | Restate: ranking vs compliance (T13), guarantees (T12); beyond G's radius change representation: fidelity cannot fix a divergent series |
| 12 | Manufacturing is physics with legal margins | Keep: the outer feasible set; floor = max(physics floor, fab floor) |
| 13 | Score physics separately from DRC | Keep: DRC sees the netlist quotient plus clearances (§6) |
| 14 | Beauty is locality of fields | Restate: locality per band, measured on cuts; below f(ℓ_m = cell) no layout closes current in a cell (CT, LS) |

### 6. What a conductor is doing

**Definition.** A piece (strip, via, pad cell, plane region) is doing whatever would change if it changed: its column of exact counterfactuals ΔB_k on every budget k, for removal and extension, per band (T4). Its jobs are the column's signs ([lens-cd](lens-cd.md) P7); "designed" or "parasitic" belongs to a (piece, job) pair. The principles fix the state that explains the column:
1. **Currents** (F2): share of each source's current, transport and induced circulation.
2. **Charges** (F1): share by driven node, and where field lines end: own return, victims, world.
3. **Energies** (F3, F6): stored, dissipated, guided (Poynting flux in its gap), radiated.
4. **Topology** (F1): bridge, shared edge, chord, ring, handle, cut member or linked; leverage ρ.
5. **Symmetry and scale** (F4, F5): imbalance χ, image validity, θ, ΔV/ΔI against Z0, ℓ_m/ℓ.
6. **Dissipation** (F6): share of each mode's damping, noise 4kT·R_b·\|H_b→y\|², heat, thermal conductance.
7. **Stress** (F4, F6): edge field, potential to neighbours, ωτ_e, damage rate.
8. **Belief** (F7): value, σ, exactness rung, lineage.

**Why a netlist cannot carry it.** A netlist collapses each connected conductor to a node ([D9](foundations-derivations.md#d9-the-netlist-as-a-quotient-6-of-foundations)). It keeps which pins share copper and drops the metric, the holes and rings that carry circulation, the world node and the band, where all eight rows live. Two layouts of one netlist differ only in what it drops: that is how an autorouter can be DRC-correct and physically wrong.

## Recommendations for our system

1. **Make G a core service:** every evaluator reports its loop gains (εQ, λ_max, g, line radius) and order, and beyond the radius promotes the coordinate rather than escalating fidelity (LS15, VP18, CD6).
2. **Tag terms self, interaction or mask (VP20), and verdicts by exactness rung;** rankings never certify compliance (IN13, IN17).
3. **Classify pieces per band by ΔV/ΔI against Z0 (LS5);** synthesize dampers (R ≈ Z0 at antinodes) wherever εQ ≥ 1 (TH1–TH4).
4. **Build the passport (CD1) from §6's eight rows,** with the world node and off-board conductors mandatory (CT16, IN6).

## Conflicts and open questions

**Contradictions between rounds, and what holds now.**

| Round 1 claim | What holds (theorem) |
|---|---|
| One adjoint prices every edit (README TL;DR, S1: dropped) | Only infinitesimal ones; slits were 13–35× off (G, T4) |
| f_x is one boundary; converters sit in the hardest regime | A length band; the open regime is DC to tens of kHz near precision analog, and slotted or finite planes (T2, T8) |
| Near-optimal is unprovable | Provable for self terms (a pour within 1.6% of its floor, F3) |
| Added copper never hurts (XD122) | Self terms only; a notch raised a coupling 22% (T3) |
| Node/loop duality; height is the strongest knob | Height is a loop lever; wide-node coupling ∝ h^0.19 (T9) |
| Cancel, then the halo shrinks (S5); imbalance accumulates (FE35) | Null planes, not smaller halos (−2%); conversion where χ changes (T9) |
| Voltage between two points; partial-L ledgers | Cycle EMFs; a shared segment's share is 30–96% by closure (T5) |
| Returns are conductors; LII without a world node | CM closes by displacement to the world (T6) |
| Decap reach 4–24 mm | Only from SRF to f_p (T8) |
| Fidelity ladder; proxies fail on near-ties | Divergent series need a new representation; nuggets fail, not smooth proxies (G, T13) |
| Invisibility is the goal | Invisible, known or designed (T10) |
| Spacing buys little below 2λ; electro-thermal is cheap | Mean ΔT only; g reaches 0.54 (F6) |
| Nine objects; twelve basis quantities | Operators of F1–F6; split M into shared-edge and field coupling, merge Bal into Vcm, add Q destination, life fraction and τ_e |

**Open.** G is shown on closed forms and toys, not on a whole board. No principle prices self and interaction terms jointly. Nonlinear victims, ESD and surge fall outside F2 (LS32). Every [C] is model against model.

## Sources

- [C]: [fd_gentleness.py](../../../tools/research/physics/fd_gentleness.py), [fd_impedance_level.py](../../../tools/research/physics/fd_impedance_level.py), reusing [th_damping_ledger.py](../../../tools/research/physics/th_damping_ledger.py) and [fe_cavity.py](../../../tools/research/physics/fe_cavity.py).
- [S]: E. Tonti, *The Mathematical Structure of Classical and Relativistic Physics*, 2013; R. M. Fano, J. Franklin Inst. 249, 1950 (Bode–Fano); V. H. Rumsey, Phys. Rev. 94, 1954.

See also: [foundations-derivations](foundations-derivations.md) · [README](README.md) · [cross-workstream-synthesis](cross-workstream-synthesis.md) · [research-gaps](research-gaps.md) · lenses [VP](lens-vp.md), [CT](lens-ct.md), [SY](lens-sy.md), [LS](lens-ls.md), [TH](lens-th.md), [IN](lens-in.md), [CD](lens-cd.md)
