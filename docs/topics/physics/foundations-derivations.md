# Foundations: derivations and the rule-of-thumb trace

**TL;DR**
- **Gentleness has a radius.** Eliminating a hidden coordinate gives the circuit a factor (I − G)⁻¹. "Circuit + parasitics" is its first-order truncation, and it converges only inside the nearest natural mode. At a resonance the radius is |δL/L| < 1/Q exactly, and the first-order error is (εQ)². On a line it is θ < ln|(m+1)/(m−1)|. For a finite edit it is the edit's collective leverage λ_max [C].
- **Impedance level is AM–GM on two energies that length ties together.** Matching must be local (sections of 100 and 25 Ω are not a 50 Ω line). For shunt structures it is one-sided: |Z| ≤ R at every frequency iff √(L/C) ≤ R. Bode–Fano bounds what any lossless network can do for a reactive load [C].
- **An interaction is the difference of two self energies** (polarization identity), so Rayleigh does not protect it and its attributions cancel.
- **The copper-only Q of a wide pair is h/max(δ, δ²/t).** One curve carries the R–L band and "copper cannot damp" [C].
- **26 common rules of thumb trace back to the principles**, each with the condition under which it holds (§R).

Symbols: θ = ωℓ/v (electrical length), T = ℓ/v (delay), Z0 = √(L′/C′), m = Z0/Z, R_s sheet resistance, δ skin depth, t copper thickness, h gap to the return, ℓ_m = R_s/(πμ0f) = δ²/t. Tags: [C] computed by [fd_gentleness.py](../../../tools/research/physics/fd_gentleness.py) or [fd_impedance_level.py](../../../tools/research/physics/fd_impedance_level.py) (seconds, uncalibrated); [I] inference; [S] secondary. Principles F1–F7, the criterion G and theorems T1–T13 are defined in [foundations](foundations.md).

## Key facts

### D1. The gentleness criterion G

Split the state into circuit unknowns x and hidden field unknowns h: A_cc·x + A_ch·h = b, A_hc·x + A_hh·h = 0. Eliminating h gives x = (I − G)⁻¹·x0 with x0 = A_cc⁻¹·b and loop gain G = A_cc⁻¹A_ch·A_hh⁻¹A_hc. Back-annotating parasitics computes x0 + G·x0, the first two terms of Σ Gⁿ·x0. This converges iff the spectral radius ρ(G) < 1, so its error is about the first neglected term. The poles of (I − G)⁻¹ are the coupled system's natural modes. The radius in any layout parameter is therefore the distance to the value at which a mode reaches the band [I].

| Hidden coordinate | Loop gain and radius | Check [C] |
|---|---|---|
| Resonant mode, δL = x·L at ω0 | H = (Q/j)/(1 + jQx): radius 1/Q; first-order relative error (Qx)² | Root test 1/Q to 5 digits for Q = 5, 30, 170; 9% error at xQ = 0.3, 81% at 0.9, partial sums diverge at 1.5 |
| Line between equal terminations Z | Zeros of 2cos θ + j(m + 1/m)sin θ at θ = j·ln((m+1)/(m−1)) + nπ | Root test within 2% of 3.04/1.61/0.69/0.20 for m = 1.1/1.5/3/10 (θ·m ≈ 2 at large m); m = 1 is exp(−jθ), an entire function |
| Plane eddy pattern of wavenumber k | Reflection 1/(1 + k·p), \|p\| = ℓ_m: the mirror series converges for kℓ_m < 1, the resistive one for kℓ_m > 1 | Complex images resum both ([lens-ls](lens-ls.md)) |
| Finite edit (removed edges B) | ΔJ = ṽᵀ(I − M)⁻¹ṽ, M = G_B^½UᵀK⁻¹UG_B^½; first order ṽᵀṽ; diag M = leverage ρ | Slit across a 24-wide strip: λ_max 0.50 → 0.977 and exact/first 2.0 → 41 as the slit grows from 1 to 22 cells; 4 → 97 Neumann terms for 10%; single exact removals summed miss the set 20× |
| Temperature | ΔT = (I − ΘD)⁻¹ΘP₀, g = ρ(D^½ΘD^½) | g = 0.16–0.54 on 1–3 W boards ([lens-th](lens-th.md)) |

The line's radius equals −ln\|Γ\| with Γ = (m−1)/(m+1): the decay per transit of the terminated line's modes. Two design moves enlarge every radius. **Matching** removes the mode (Γ = 0). **Damping** moves it off the real axis: lowering a mode from copper's Q of 30–170 to Q ≈ 1 multiplies the tolerable ε by Q_cu/Q. That is why T1 and T10 are one idea.

### D2. Impedance level (T1)

1. **Energy.** A uniform go/return piece has L = Z0·T and C = T/Z0. With current swing ΔI and voltage swing ΔV it stores E = ½T(Z0·ΔI² + ΔV²/Z0) ≥ T·ΔV·ΔI, with equality iff Z0 = ΔV/ΔI ([lens-vp](lens-vp.md) D6, PW2).
2. **First order.** Between equal real terminations, H/H0 = 1/(cos θ + j·½(m + 1/m)·sin θ). The first-order term is a pure phase θ(m + 1/m)/2 ≥ θ. Amplitude error enters at second order, −(θ²/8)(m − 1/m)² ([lens-ls](lens-ls.md)). At m = 1 the piece is exp(−jθ) at any length.
3. **Locality.** For sections in series, (ΣL)(ΣC) = (Σ Z_iT_i)(Σ T_i/Z_i) ≥ (ΣT_i)², with equality iff all Z_i are equal (Cauchy–Schwarz). Sections of 100 and 25 Ω have √(L/C) = 50 Ω but L·C = 1.56 T² and a first-order phase 1.25θ [C].
4. **Constant resistance (shunt form).** For (R + jωL) ∥ (R + 1/jωC) with X = ωL − 1/ωC, |Z|² = ((R² + Z0²)² + R²X²)/(4R² + X²). So |Z| = R at every ω iff Z0 = R, and |Z| ≤ R at every ω iff Z0 ≤ R. At R = 0.1·Z0 the peak is 50R [C]. A PDN meets a target Z_t when each stage's √(L/C) ≤ Z_t and its damping R ≈ Z_t (Zobel's network [S]; controlled ESR, PDN-10).
5. **Damping.** A series RLC has Q = Z0/R and a parallel one Q = R/Z0, so Q = 1 at R = Z0. The parallel-plate Z0 of a p-wide strip of a plane pair is η·d/p, which is exactly TH's matched edge resistor η0·d/(√εr·p). With it, the 100 × 80 mm cavity keeps no resonant peak, only an inductive rise ∝ d: 0.39 Ω at 1 GHz for d = 0.1 mm. Bare peaks equal max Q_mn·Z0_mn within 0–8% (Z0_mn = d·φ²/(ab·ε·ω_mn); 137 mΩ at 0.1 mm) [C].
6. **Bode–Fano [S].** For a load R ∥ C, ∫₀^∞ ln(1/\|Γ\|)dω ≤ π/(RC). A flat match over 0–f_max therefore has \|Γ\| ≥ exp(−1/(2f_max·RC)). For 50 Ω ∥ 1 pF this is 0.135 at 5 GHz and 0.54 at 16 GHz [C]. Invisibility of a reactance over a band costs loss or bandwidth.
7. **Capacitive node.** If Z = 1/(jωC_n), then ε_C = C_piece/C_n (no frequency) and ε_L = ω²L·C_n. High-Z rules reduce to a capacitance ratio: 15 mm × 0.15 mm gives 1.53 pF over a plane at 0.1 mm and 0.55 pF with the plane voided [C].
8. **Buck pieces** (12 V, 10 A, 2 ns, h = 0.1 mm, f_e = 159 MHz) [C]:

   | Piece | ΔV/ΔI | Best width | Energy per edge |
   |---|---|---|---|
   | VIN pour (CIN holds VIN) | 0.15 Ω | widest: Z0 1.2 Ω at 15 mm | 70 → 1.7 nJ (0.15 → 15 mm) |
   | SW inside the loop | 1.2 Ω | 15 mm (Z0 = V/I) | 5.5 nJ at 2 mm, 1.65 at 15 (floor 1.55) |
   | SW to inductor | ≈ 200 Ω | narrowest | 0.05 nJ; DC current sets the width |

   Parts hold 22 nJ (½C_oss·V², 300 pF) and 25 nJ (½L_pkg·I², 0.5 nH). Widening the SW piece from 2 to 15 mm multiplies its external dipole 2ε0·V·A by 7.5. The interaction term overrules the self optimum.
9. **Why planes treat loops and nodes differently [I].** In the gentle regime (ε ≪ 1) a loop's current is fixed by the circuit and a node's voltage is fixed by its source. An image halves the moment arm: a loop's moment 2I·h falls with h. A wide node's charge εAV/h rises as h falls, so its moment 2εAV stays put. This is why [lens-sy](lens-sy.md) D1 finds h^1.98 for mutual L and h^0.19 for wide-strip mutual C. Narrow strips (charge ∝ 1/ln(4h/w)) sit between, at h^0.74. Outside the gentle regime the roles swap: a loop dominated by its own L is voltage-forced.

### D3. Self versus interaction (T3)

For a reciprocal band with K = Kᵀ, a self quantity is Z(s) = sᵀK⁻¹s and a coupling is Z_pq = s_qᵀK⁻¹s_p = ¼[Z(s_p + s_q) − Z(s_p − s_q)]. In a pure R or L regime added copper lowers both self terms (F3), so their difference has no sign. Every per-piece attribution of Z_pq is likewise a difference of two non-negative attributions. Hence the cancellation index χ = 0.08–0.10 for hot loop → ADC and +3% from the worst added via ([lens-cd](lens-cd.md) D2). Mutual inductance is ¼(L_aiding − L_opposing). An EMI mask is a maximum over frequency of a transfer, neither form (class C, [lens-vp](lens-vp.md)).

### D4. Exact edit pricing (T4)

Removing edges B with conductances D changes J by vᵀ(D⁻¹ − UᵀK⁻¹U)⁻¹v (Woodbury). For one uncoupled piece this is a/(1 − ρ), where a is the attribution and ρ its spanning-tree probability ([lens-cd](lens-cd.md) D1). **Two different factors of 2:** an interior piece of a sheet has ρ = ½, so removal costs twice its first-order price (a disc hole's polarizability is 2 × area). Separately, an edge notch costs twice an interior slit of the same intercepted current, by mirror symmetry ([lens-ct](lens-ct.md), [lens-sy](lens-sy.md)). A slit removes no area while its pieces' collective leverage tends to 1. The finite limit is the crack polarizability, ΔJ = (π/4)R_s·Δψ_u·Δψ_λ for any objective ([lens-sy](lens-sy.md) D3), and in a strip (2/π)R_s·ln sec(πx/2).

### D5. Cycles, gauge and Kelvin (T5)

∮_γE·dl = −jωΦ_γ depends on the cycle γ only. Splitting it into segment voltages fixes a gauge (partial inductance takes A → 0 at infinity), so a segment's "bounce" changes with the victim's closure: 30–96% of L_p ([lens-ct](lens-ct.md) D4). By Tellegen, a load p puts V_err = Σ_b s_b^q·v_b^p on sense port q. This is zero when the sense cycle's pieces carry none of p's drop: Kelvin at every band ([lens-cd](lens-cd.md) D4).

### D6. The world node (T6)

Take a closed surface S around the board, pierced by one cable. F1 gives Σ cable currents = −jω·Q_S. In the capacitance matrix with the outside as one more conductor, the mutual terms between board conductors cancel. Hence I_CM = −jω·Σ_i C_i,ext·V_i ([lens-ct](lens-ct.md) D2). Without the world node, KCL on S forces I_CM = 0, so a world-free extraction is blind to voltage-driven common mode (CT16).

### D7. One length, one Q curve (T2, T8)

Use ℓ_m = R_s/(πμ0f) = δ²/t as the canonical plane length. [Lens-vp](lens-vp.md)'s ℓ50 and [lens-sy](lens-sy.md)'s ℓ_d equal ℓ_m/2, and f_x = R_s/(2πμ0h) is ℓ_m = 2h. A wide go/return pair has L = μ0h and R = 2R_s(f) per square, so Q_cu = h/max(δ, δ²/t). This is within 0.93–1.30 of the exact slab model from 0.1·f_x to 1 GHz, and the 1.23 at low f is internal inductance [C]. Q_cu ≈ ½ at f_x (exact 0.51–0.62), rises ∝ f up to the skin frequency, then as √f to h/δ = 30–170 ([lens-th](lens-th.md) D1). The return localizes where Q_cu exceeds about 1. Wide copper therefore either confines its return or damps itself, not both [I].

### D8. Loss versus damage (T11)

Near a wedge of interior angle α, J ∝ r^(π/α−1) ([lens-sy](lens-sy.md) P6). ∫\|J\|²·r·dr converges for every α ≤ 2π, so a corner adds a bounded loss (0.56 squares for 90°). The peak diverges for α > π, so local high-p damage measures see it. Heat diffusion smooths it once √(κt) exceeds the width w (κ: copper's thermal diffusivity), which gives the pulse threshold t* = w²/κ ([lens-th](lens-th.md) D7).

### D9. The netlist as a quotient (§6 of foundations)

Let X be the copper complex: pieces, adjacency, vias, and displacement edges to references and the world. A netlist is X/∼, each connected conductor collapsed to one node. It keeps H0 (which pins share copper) and drops the metric (R, L, C), H1 (holes, rings, handles that carry circulation), the world node and the band dependence. Two layouts with one netlist differ only in what the quotient drops, so no netlist rule can rank them. DRC adds clearances between conductors, not the fields they guide.

### R. Rule-of-thumb trace

| Rule | Theorem (principle) | Holds when / fails when |
|---|---|---|
| Return flows under the trace; don't cross splits | T8, T7 (F5, F4, F1) | Above f_x with an intact reference; below it the return spreads |
| Minimize loop area | T1, T9 (F4) | Free space; over a plane, height × squares (moment with image) |
| Thin prepreg under hot loops | T1, T9 (F3, F5) | Current-forced loops; does not cut wide-node coupling |
| Keep the switch node small | T3 (F2, F4) | External dipole ∝ ∫V·dA; DC current sets the minimum width |
| Wide copper for power | T1, floors (F3) | Self terms; extra C is harmless on held rails |
| Decap as close as possible | T8 wire medium (F5) | Within the screening length, SRF to f_p; mounting L is logarithmic |
| Stitch every λ/20 | T8, T10 (F5, F6) | Raises modes to √(f_mn² + f_p²) and screens below f_p; damps nothing: add terminations |
| 3W spacing | T8 decay class (F5) | Microstrip with w/h ≈ 2 encodes D/h by accident ([lens-in](lens-in.md)) |
| Series-terminate fast drivers | T1 (F5) | R_s = Z0 makes the line a delay at any length |
| Critical length t_r/6 or t_r/2 | G (F5) | Depends on R_s/Z0 and the overshoot budget (LS7) |
| No right angles, 45° | T11 (F4, F6) | Damage only (HV, pulses < w²/κ, fusing) or multi-GHz; never steady loss |
| Star or single-point ground | T7 (F1, F5) | Articulation is exact at DC; at HF a single tie feeds the cable antenna |
| Split AGND/DGND | T7, T5 (F1) | As a cut of DC transport only, crossed at the neck, never under fast signals |
| Kelvin sensing | T5 (F1) | Sense cycle carries none of the load's drop, every band |
| Connectors on one edge | T6, lead field (F1, F2) | Removes the antenna arm between cable points (about 40 dB) |
| Bond heatsink or chassis at RF | T6 (F1) | Moves the displacement edge inside; the bond's L limits it (−39 dB at 30 MHz, −20 at 100) |
| Snubber at the switch, R = √(L/C_oss) | T10, T1 (F6) | R = Z0 gives Q ≈ 1; tuning L_s·C_s ≈ L·C_oss cuts the loss by two thirds |
| Controlled-ESR decaps | T1 shunt form (F6) | Every stage √(ESL/C) ≤ Z_t with ESR ≈ Z_t |
| Symmetric pairs, length matching | T9 (F4) | Conversion is at changes of χ; fix asymmetry where it is |
| Guard high-Z inputs | T1, F6 | Cuts leakage and effective C; dielectric noise survives (TH14) |
| Void the plane under a high-Z or RF pad | T1 (F5) | Moves Z0 toward Z; costs shielding (an interaction) |
| Pour all unused copper | T3 (F3) | Safe for self terms; can raise couplings (CD24, VP22) |
| Thermal vias under hot parts | F6 | Heat path = electrical element: 261 K/W per via is 1.74 mΩ ÷ L·T |
| Spread hot parts | F6 | Mean ΔT only beyond about 2λ; swing, hogging and plumes differ |
| Isothermal layout for precision | F6 (Onsager) | EMF = ∮S∇T·dl; pad symmetry removes the I² term, not Peltier |
| One via per amp | F3 capacity floor ([lens-vp](lens-vp.md) D3) | Via sets act by capacity (outer size); edge vias carry the current. Heating is bounded by ΔT = V²/(8·L0·T) for an end-cooled barrel (Wiedemann–Franz, L0 the Lorenz number): 1 A gives 0.03 K ([derivation-audit](derivation-audit.md)) |

## Recommendations for our system

- Keep these derivations as regression tests: each [C] line above is a closed form checked by script, so a solver change that breaks one is a bug.
- Store the "Holds when" column of §R as each rule record's regime predicate (RG1–RG3).

## Conflicts and open questions

- G is shown on closed forms and toy networks. The block-elimination argument needs a linear coupled system; switching and nonlinear victims need the periodic or transient version.
- D2.9 is an inference from [lens-sy](lens-sy.md)'s slopes; a sweep at fixed charge (floating nodes) would test it.
- The buck numbers use assumed CIN ESL, C_oss and inductor capacitance.

## Sources

- [C]: [fd_gentleness.py](../../../tools/research/physics/fd_gentleness.py), [fd_impedance_level.py](../../../tools/research/physics/fd_impedance_level.py), reusing [th_damping_ledger.py](../../../tools/research/physics/th_damping_ledger.py) and [fe_cavity.py](../../../tools/research/physics/fe_cavity.py).
- [S]: R. M. Fano, J. Franklin Inst. 249, 1950 (Bode–Fano); O. J. Zobel, Bell Syst. Tech. J. 2, 1923 (constant-resistance networks); B. D. H. Tellegen, Philips Res. Rep. 7, 1952; Jackson, *Classical Electrodynamics* §3.4 (wedges).
- Round-2 lens docs, linked inline.

See also: [foundations](foundations.md) · [lens-ls](lens-ls.md) · [lens-th](lens-th.md) · [lens-cd](lens-cd.md) · [lens-sy](lens-sy.md) · [lens-vp](lens-vp.md) · [lens-ct](lens-ct.md) · [lens-in](lens-in.md)
