# Foundations: derivations and the rule-of-thumb trace

Scope: derivations D1–D9 of the gentleness criterion G and theorems T1–T11, and the trace of 26 rules of thumb to theorems. Not here: principle and theorem statements -> [foundations](foundations.md); symbols (θ, T, Z0, m, R_s, δ, t, h, ℓ_m) -> [vocabulary](vocabulary.md#glossary).
Keys: gentleness radius, Neumann series, loop gain, spectral radius, AM-GM, Cauchy-Schwarz, constant resistance, Zobel, Bode-Fano, polarization identity, Woodbury, leverage, crack polarizability, Tellegen, gauge, world node, Q_cu, f_x, wedge singularity, netlist quotient, rule-of-thumb trace

[C] = [fd_gentleness.py](../../../tools/research/physics/fd_gentleness.py) or [fd_impedance_level.py](../../../tools/research/physics/fd_impedance_level.py) (seconds, uncalibrated). Keep each [C] line as a regression test: a solver change that breaks one is a bug.

## D1. The gentleness criterion G

State = circuit unknowns x + hidden field unknowns h: A_cc·x + A_ch·h = b, A_hc·x + A_hh·h = 0. Eliminating h: x = (I − G)⁻¹·x0, x0 = A_cc⁻¹·b, loop gain G = A_cc⁻¹A_ch·A_hh⁻¹A_hc. Back-annotation computes x0 + G·x0 (first two terms of Σ Gⁿ·x0); converges iff ρ(G) < 1; error ≈ first neglected term. Poles of (I − G)⁻¹ = natural modes of the coupled system, so the radius in any layout parameter = distance to the value at which a mode reaches the band [I].

| Hidden coordinate | Loop gain and radius | Check [C] |
|---|---|---|
| Resonant mode, δL = x·L at ω0 | H = (Q/j)/(1 + jQx): radius 1/Q; first-order relative error (Qx)² | Root test 1/Q to 5 digits for Q = 5, 30, 170; 9% error at xQ = 0.3, 81% at 0.9; partial sums diverge at 1.5 |
| Line between equal terminations Z | Zeros of 2cos θ + j(m + 1/m)sin θ at θ = j·ln((m+1)/(m−1)) + nπ | Root test within 2% of 3.04/1.61/0.69/0.20 for m = 1.1/1.5/3/10 (θ·m ≈ 2 at large m); m = 1 is exp(−jθ), entire |
| Plane eddy pattern, wavenumber k | Reflection 1/(1 + k·p), \|p\| = ℓ_m: mirror series converges for kℓ_m < 1, resistive one for kℓ_m > 1 | Complex images resum both ([lens-ls](lens-ls.md)) |
| Finite edit (removed edges B) | ΔJ = ṽᵀ(I − M)⁻¹ṽ, M = G_B^½UᵀK⁻¹UG_B^½; first order ṽᵀṽ; diag M = leverage ρ | Slit across a 24-wide strip, 1 → 22 cells (92%): λ_max 0.50 → 0.977, exact/first 2.0 → 41; 4 → 97 Neumann terms for 10%; single exact removals summed miss the set 20× |
| Temperature | ΔT = (I − ΘD)⁻¹ΘP₀, g = ρ(D^½ΘD^½) | g = 0.16–0.54 on 1–3 W boards ([lens-th](lens-th.md)) |

Line radius = −ln\|Γ\|, Γ = (m−1)/(m+1): decay per transit of the terminated line's modes. Two moves enlarge every radius: **matching** removes the mode (Γ = 0); **damping** moves it off the real axis (Q 30–170 of copper → Q ≈ 1 multiplies tolerable ε by Q_cu/Q). Hence T1 and T10 are one idea.

## D2. Impedance level (T1)

1. **Energy.** Uniform go/return piece: L = Z0·T, C = T/Z0. Stores E = ½T(Z0·ΔI² + ΔV²/Z0) ≥ T·ΔV·ΔI, equality iff Z0 = ΔV/ΔI (AM–GM; [lens-vp](lens-vp.md) D6, PW2).
2. **First order.** Between equal real terminations H/H0 = 1/(cos θ + j·½(m + 1/m)·sin θ): first-order term pure phase θ(m + 1/m)/2 ≥ θ; amplitude error second order, −(θ²/8)(m − 1/m)² ([lens-ls](lens-ls.md)). m = 1: exp(−jθ) at any length. 50 Ω line tolerates ±10% in Z0 at ≤ 0.05 dB [C].
3. **Locality.** Sections in series: (ΣL)(ΣC) = (Σ Z_iT_i)(Σ T_i/Z_i) ≥ (ΣT_i)², equality iff all Z_i equal (Cauchy–Schwarz). 100 + 25 Ω sections: √(L/C) = 50 Ω but L·C = 1.56T², first-order phase 1.25θ [C].
4. **Constant resistance (shunt form).** (R + jωL) ∥ (R + 1/jωC), X = ωL − 1/ωC: \|Z\|² = ((R² + Z0²)² + R²X²)/(4R² + X²). \|Z\| = R at every ω iff Z0 = R; \|Z\| ≤ R at every ω iff Z0 ≤ R. R = 0.1·Z0: peak 50R [C]. PDN meets Z_t when each stage's √(L/C) ≤ Z_t with damping R ≈ Z_t (Zobel [S]; controlled ESR, PDN-10).
5. **Damping.** Series RLC Q = Z0/R, parallel Q = R/Z0: Q = 1 at R = Z0. Parallel-plate Z0 of a p-wide strip of a plane pair = η·d/p = TH's matched edge resistor η0·d/(√εr·p). With it the 100 × 80 mm cavity keeps no resonant peak, only an inductive rise ∝ d: 0.39 Ω at 1 GHz for d = 0.1 mm. Bare peaks = max Q_mn·Z0_mn within 0–8% (Z0_mn = d·φ²/(ab·ε·ω_mn); 137 mΩ at 0.1 mm) [C].
6. **Bode–Fano [S].** Load R ∥ C: ∫₀^∞ ln(1/\|Γ\|)dω ≤ π/(RC), so a flat match over 0–f_max has \|Γ\| ≥ exp(−1/(2f_max·RC)). 50 Ω ∥ 1 pF: 0.135 at 5 GHz, 0.54 at 16 GHz [C]. Invisibility of a reactance over a band costs loss or bandwidth.
7. **Capacitive node.** Z = 1/(jωC_n): ε_C = C_piece/C_n (frequency-free), ε_L = ω²L·C_n. High-Z rules reduce to a capacitance ratio: 15 mm × 0.15 mm = 1.53 pF over a plane at 0.1 mm, 0.55 pF with the plane voided [C]. A 1 MΩ node sits at m ≈ 10⁻⁴: only its C matters [C].
8. **Buck pieces** (12 V, 10 A, 2 ns, h = 0.1 mm, f_e = 159 MHz) [C]:

   | Piece | ΔV/ΔI | Best width | Energy per edge |
   |---|---|---|---|
   | VIN pour (CIN holds VIN) | 0.15 Ω | widest: Z0 1.2 Ω at 15 mm | 70 → 1.7 nJ (0.15 → 15 mm) |
   | SW inside the loop | 1.2 Ω | 15 mm (Z0 = V/I) | 5.5 nJ at 2 mm, 1.65 at 15 (floor 1.55): ~4 nJ at stake |
   | SW to inductor | ≈ 200 Ω | narrowest | 0.05 nJ; DC current sets the width |

   Parts hold 22 nJ (½C_oss·V², 300 pF) and 25 nJ (½L_pkg·I², 0.5 nH). Widening SW 2 → 15 mm multiplies its external dipole 2ε0·V·A by 7.5: the interaction term overrules the self optimum. Assumed CIN ESL, C_oss and inductor capacitance.
9. **Planes treat loops and nodes differently [I].** Gentle regime (ε ≪ 1): loop current fixed by the circuit, node voltage fixed by its source. An image halves the moment arm: loop moment 2I·h falls with h; wide node charge εAV/h rises as h falls, so its moment 2εAV stays. Hence [lens-sy](lens-sy.md) D1: mutual L ∝ h^1.98, wide-strip mutual C ∝ h^0.19; narrow strips (charge ∝ 1/ln(4h/w)) h^0.74. Outside the gentle regime roles swap: a loop dominated by its own L is voltage-forced. Untested: a sweep at fixed charge (floating nodes) would test it.

## D3. Self versus interaction (T3)

Reciprocal band, K = Kᵀ: self Z(s) = sᵀK⁻¹s; coupling Z_pq = s_qᵀK⁻¹s_p = ¼[Z(s_p + s_q) − Z(s_p − s_q)] (polarization identity). In a pure R or L regime added copper lowers both self terms (F3), so their difference has no sign, and Rayleigh does not protect it. Every per-piece attribution of Z_pq is a difference of two non-negative attributions: cancellation index χ = 0.08–0.10 for hot loop → ADC, +3% from the worst added via ([lens-cd](lens-cd.md) D2). Mutual inductance = ¼(L_aiding − L_opposing). An EMI mask (max over frequency of a transfer) is neither form (class C, [lens-vp](lens-vp.md)).

## D4. Exact edit pricing (T4)

Removing edges B with conductances D: ΔJ = vᵀ(D⁻¹ − UᵀK⁻¹U)⁻¹v (Woodbury). One uncoupled piece: a/(1 − ρ), a = attribution, ρ = spanning-tree probability ([lens-cd](lens-cd.md) D1). **Two different factors of 2:** (i) interior sheet piece ρ = ½, so removal costs twice its first-order price (disc hole polarizability = 2 × area); (ii) an edge notch costs twice an interior slit of the same intercepted current, by mirror symmetry ([lens-ct](lens-ct.md), [lens-sy](lens-sy.md)). A slit removes no area while its pieces' collective leverage → 1; finite limit = crack polarizability ΔJ = (π/4)R_s·Δψ_u·Δψ_λ for any objective ([lens-sy](lens-sy.md) D3); in a strip (2/π)R_s·ln sec(πx/2).

## D5. Cycles, gauge and Kelvin (T5)

∮_γE·dl = −jωΦ_γ depends on the cycle γ only. Segment voltages fix a gauge (partial inductance takes A → 0 at infinity), so a segment's "bounce" changes with the victim's closure: 30–96% of L_p ([lens-ct](lens-ct.md) D4). Tellegen: load p puts V_err = Σ_b s_b^q·v_b^p on sense port q; zero when the sense cycle's pieces carry none of p's drop = Kelvin at every band ([lens-cd](lens-cd.md) D4).

## D6. The world node (T6)

Closed surface S around the board, pierced by one cable: F1 gives Σ cable currents = −jω·Q_S. With the outside as one more conductor in the capacitance matrix, mutual terms between board conductors cancel: I_CM = −jω·Σ_i C_i,ext·V_i ([lens-ct](lens-ct.md) D2). Without the world node KCL on S forces I_CM = 0: a world-free extraction is blind to voltage-driven common mode (CT16).

## D7. One length, one Q curve (T2, T8)

Canonical plane length ℓ_m = R_s/(πμ0f) = δ²/t. [Lens-vp](lens-vp.md)'s ℓ50 and [lens-sy](lens-sy.md)'s ℓ_d = ℓ_m/2; f_x = R_s/(2πμ0h) is ℓ_m = 2h. Wide go/return pair: L = μ0h, R = 2R_s(f) per square, so **Q_cu = h/max(δ, δ²/t)**: within 0.93–1.30 of the exact slab model from 0.1·f_x to 1 GHz (1.23 at low f = internal inductance) [C]. Q_cu ≈ ½ at f_x (exact 0.51–0.62), rises ∝ f up to the skin frequency, then ∝ √f to h/δ = 30–170 ([lens-th](lens-th.md) D1). Return localizes where Q_cu > ~1: wide copper confines its return or damps itself, not both [I]. One curve carries the R–L band and "copper cannot damp".

## D8. Loss versus damage (T11)

Wedge of interior angle α: J ∝ r^(π/α−1) ([lens-sy](lens-sy.md) P6). ∫\|J\|²·r·dr converges for every α ≤ 2π: a corner adds bounded loss (0.56 squares for 90°). Peak diverges for α > π: local high-p damage measures see it. Heat diffusion smooths it once √(κt) > w (κ copper thermal diffusivity): pulse threshold t* = w²/κ ([lens-th](lens-th.md) D7).

## D9. The netlist as a quotient (§5 of foundations)

X = copper complex (pieces, adjacency, vias, displacement edges to references and the world). Netlist = X/∼, each connected conductor collapsed to one node. Keeps H0 (which pins share copper); drops metric (R, L, C), H1 (holes, rings, handles carrying circulation), world node, band dependence. Two layouts with one netlist differ only in what the quotient drops: no netlist rule can rank them. DRC adds clearances between conductors, not the fields they guide.

## R. Rule-of-thumb trace

"Holds when" = each rule record's regime predicate (RG1–RG3).

| Rule | Theorem (principle) | Holds when / fails when |
|---|---|---|
| Return flows under the trace; don't cross splits | T8, T7 (F5, F4, F1) | Above f_x with an intact reference; below it the return spreads |
| Minimize loop area | T1, T9 (F4) | Free space; over a plane, height × squares (moment with image) |
| Thin prepreg under hot loops | T1, T9 (F3, F5) | Current-forced loops; does not cut wide-node coupling |
| Keep the switch node small | T3 (F2, F4) | External dipole ∝ ∫V·dA; DC current sets the minimum width |
| Wide copper for power | T1, floors (F3) | Self terms; extra C is harmless on held rails |
| Decap as close as possible | T8 wire medium (F5) | Within the screening length, SRF to f_p; mounting L is logarithmic |
| Stitch every λ/20 | T8, T10 (F5, F6) | Raises modes to √(f_mn² + f_p²), screens below f_p; damps nothing: add terminations |
| 3W spacing | T8 decay class (F5) | Microstrip with w/h ≈ 2 encodes D/h by accident ([lens-in](lens-in.md)) |
| Series-terminate fast drivers | T1 (F5) | R_s = Z0 makes the line a delay at any length |
| Critical length t_r/6 or t_r/2 | G (F5) | Depends on R_s/Z0 and the overshoot budget (LS7) |
| No right angles, 45° | T11 (F4, F6) | Damage only (HV, pulses < w²/κ, fusing) or multi-GHz; never steady loss |
| Star or single-point ground | T7 (F1, F5) | Articulation exact at DC; at HF a single tie feeds the cable antenna |
| Split AGND/DGND | T7, T5 (F1) | As a cut of DC transport only, crossed at the neck, never under fast signals |
| Kelvin sensing | T5 (F1) | Sense cycle carries none of the load's drop, every band |
| Connectors on one edge | T6, lead field (F1, F2) | Removes the antenna arm between cable points (6–30 dB by a lumped estimate; the earlier "about 40 dB" was a script input, [verification-and-limits](verification-and-limits.md#2-script-and-quantity-scopes)) |
| Bond heatsink or chassis at RF | T6 (F1) | Moves the displacement edge inside; bond L limits it (−39 dB at 30 MHz, −20 at 100) |
| Snubber at the switch, R = √(L/C_oss) | T10, T1 (F6) | R = Z0 gives Q ≈ 1; tuning L_s·C_s ≈ L·C_oss cuts the loss by two thirds |
| Controlled-ESR decaps | T1 shunt form (F6) | Every stage √(ESL/C) ≤ Z_t with ESR ≈ Z_t |
| Symmetric pairs, length matching | T9 (F4) | Conversion is at changes of χ; fix asymmetry where it is |
| Guard high-Z inputs | T1, F6 | Cuts leakage and effective C; dielectric noise survives (TH14) |
| Void the plane under a high-Z or RF pad | T1 (F5) | Moves Z0 toward Z; costs shielding (an interaction) |
| Pour all unused copper | T3 (F3) | Safe for self terms; can raise couplings (CD24, VP22) |
| Thermal vias under hot parts | F6 | Heat path = electrical element: 261 K/W per via is 1.74 mΩ ÷ L·T |
| Spread hot parts | F6 | Mean ΔT only beyond about 2λ; swing, hogging and plumes differ |
| Isothermal layout for precision | F6 (Onsager) | EMF = ∮S∇T·dl; pad symmetry removes the I² term, not Peltier |
| One via per amp | F3 capacity floor ([lens-vp](lens-vp.md) D3) | Via sets act by capacity (outer size); edge vias carry the current. End-cooled barrel heating ≤ ΔT = V²/(8·L0·T) (Wiedemann–Franz, L0 Lorenz number): 1 A gives 0.03 K ([derivation-audit](derivation-audit.md)) |

## Open questions

- G shown on closed forms and toy networks. Block elimination needs a linear coupled system; switching and nonlinear victims need the periodic or transient version.
- D2.9 is inferred from [lens-sy](lens-sy.md)'s slopes.

## Sources

- [C]: [fd_gentleness.py](../../../tools/research/physics/fd_gentleness.py), [fd_impedance_level.py](../../../tools/research/physics/fd_impedance_level.py), reusing [th_damping_ledger.py](../../../tools/research/physics/th_damping_ledger.py) and [fe_cavity.py](../../../tools/research/physics/fe_cavity.py).
- [S]: R. M. Fano, J. Franklin Inst. 249, 1950 (Bode–Fano); O. J. Zobel, Bell Syst. Tech. J. 2, 1923 (constant-resistance networks); B. D. H. Tellegen, Philips Res. Rep. 7, 1952; Jackson, *Classical Electrodynamics* §3.4 (wedges).
