# Lens LS: locality, causality, scales and the circuit limit

**TL;DR**
- **A circuit is Maxwell at zeroth order inside a window with four edges:** θ = ωℓ/v, Z/Z0, ℓ_m/ℓ (plane resolution) and ωτ_e (insulator relaxation). On a PCB the window is huge (η0/R_s ≈ 7.7×10⁵ for 1 oz), and layout is where structures approach an edge. Both first-order corrections are θ·(Z0/Z)^±1. Their product θ² depends only on length, and at Z0 = Z they reduce to a pure delay. This derives PW2, principle 3 and node/loop duality, and it turns t_r/6-vs-t_r/2 into a family [C].
- **A copper plane is a spatial low-pass filter.** It mirrors patterns larger than ℓ_m(f) = R_s/(πμ0f) = δ²/t, and in the time domain it is an image receding at 2R_s/μ0 (782 m/s for 1 oz). f_x and the loop-mirror onset are two ends of one band. On intact planes, 4–6 complex images fall within 0.5–3.5% of the exact result, where the perfect image is up to 79% off [C]. That closes most of round 1's Tier-1 gap 2.
- **Decap fields and stitching lattices are one wire medium:** ω² = ω_p² + v²k², with ω_p² = n/(L_post·C′). The field screens below ω_p (decap reach, stitching attenuation). At ω_p sits the PDN anti-resonance (k = 0). Above it, modes sit at √(f_mn² + f_p²). A lattice check agrees within 0–3% [C].
- **Every interaction has a decay class and a natural length** (about 20 lengths from 1 µm to 5 m). Measure distance as r/ℓ_q, and above cut-off use position on the mode shapes instead.
- **"Circuit + parasitics" is a perturbation series.** It diverges where a small parameter meets a Q, a diffusion kernel, radiation or a field singularity. There the representation must switch. The order a victim needs is n* ≈ ln(B/S)/ln ε: 1 for digital, 3 for 16-bit and 4 for 24-bit at ε = 0.01.

Tags: [P], [S], [I] as usual. [C] numbers come from [ls_thin_sheet.py](../../../tools/research/physics/ls_thin_sheet.py), [ls_post_lattice.py](../../../tools/research/physics/ls_post_lattice.py) and [ls_regime_map.py](../../../tools/research/physics/ls_regime_map.py). LS ids are in the [lens-ls ideas](../../ideas/physics-first/lens-ls.md).

## Key facts

### 1. Principles

| # | Principle | Statement |
|---|---|---|
| P1 | Quasi-static limit | θ = ωℓ/v ≪ 1 gives EQS or MQS ([Haus & Melcher §3.3](https://ocw.mit.edu/courses/res-6-001-electromagnetic-fields-and-energy-spring-2008/pages/chapter-3/) [S]). KCL and KVL are order 0, exact with displacement and flux edges ([lens-ct](lens-ct.md)). τ_e·τ_m = (ℓ/v)² [I] |
| P2 | Impedance-level split | For Z0 = √(L′/C′) and circuit level Z = V/I: ε_L = θ·Z0/Z breaks KVL, ε_C = θ·Z/Z0 breaks KCL (CT26's K_L, K_C). ε_L·ε_C = θ² and ε_L + ε_C ≥ 2θ, with equality at Z0 = Z |
| P3 | Conductor imperfection | ε_R = R/Z. A thin sheet reflects wavenumber k by Γ = 1/(1 − jkℓ_m), ℓ_m = 2R_s/(ωμ0) = δ²/t; its image recedes at 2/(μ0σt) ([Liu & Belcher eq. 1](https://arxiv.org/abs/0712.0182) [P]) |
| P4 | Insulator imperfection | ωτ_e with τ_e = ε/σ, or ε_eff·g/σ_s for a surface gap. Below 1/τ_e, conductivity sets fields and leakage |
| P5 | Locality | Sheets obey ∇²u = γ²u, γ² = Z_s·Y_p: Re > 0 screens, Re < 0 propagates, arg ≈ π/2 diffuses. The magnetic sheet is non-local (\|k\|). Open space decays by multipole order; images raise it |
| P6 | Causality | Delay is ℓ/v and f_knee ≈ 0.35/t_r. Kramers–Kronig: dε′/d ln ω = −(2/π)·ε″ |
| P7 | Scale separation | Homogenize when pitch ≪ field length; average when τ_fast ≪ τ_slow. A model's error is its first neglected term |

### 2. Derivation A: the impedance split

L = Z0·ℓ/v and C = ℓ/(Z0·v), so ωLI/V = θ·Z0/Z and ωCV/I = θ·Z/Z0. For a short line between equal terminations Z, with m = Z0/Z:
- the transfer is H = 1/(2cos θ + j sin θ·(m + 1/m));
- the amplitude error is |H|/|H0| − 1 ≈ −(θ²/8)(m − 1/m)²: zero at m = 1, −2.93% (series −3.06%) at θ = 0.05, m = 10 [C];
- the phase is θ(m + 1/m)/2, and the series fails near θ·m ≈ 2.

| Consequence | Explains |
|---|---|
| Minimum ε_L + ε_C at Z0 = Z | PW2's Z0* = V/I |
| θ² is independent of width and height | Principle 3: L·C = l²/v², "only length lowers all three" |
| Loops have Z ≪ Z0; nodes have Z ≫ Z0 | Principle 2 and LA4. The variable is Z/Z0 |
| PCB Z0 spans ≈ 0.5 Ω (30 mm plane pair at 0.1 mm) to ~170 Ω; circuits span mΩ to GΩ | Plane pairs for the PDN; void the plane under high-Z inputs (LA36). Height should move Z0 toward Z |
| A series-matched line is a pure delay at any length: 0% overshoot [C] | "Series-terminate"; the critical-length family (§6) |

### 3. Derivation B: the plane as a spatial filter

K = σ_s·E and A = μ0K/(2|k|) give K(k) = −I·F(k)·e^{−kh}·Γ(k), with Γ = 1/(1 + kp) and p = 2R_s/(jωμ0) [I; thin-sheet Dodd–Deeds]. Patterns larger than ℓ_m are mirrored; finer ones are blurred.
- **One law, three crossovers.**
  - ℓ_m = 2h is f_x.
  - ℓ_m = a is the loop onset (PW24).
  - ℓ_m = W (2–4 kHz on 60 mm) makes the plane resistive at board scale.

  ℓ_m is 124 mm at 1 kHz and 0.124 mm at 1 MHz for 1 oz [C]. [lens-sy](lens-sy.md) found the same length (ℓ_d = ℓ_m/2).
- **A band, not a frequency.** A structure spanning h to a is mirrored scale by scale. For a 10 mm loop at h = 0.1 mm the band runs from 12 kHz to 0.6 MHz, and half-mirroring falls at a/ℓ_m = 1.3–4.5 [C].
- **Checks.** The share within ±3h collapses onto ℓ_m/h (0.342 / 0.760 / 0.794 at 10 / 1 / 0.3, any h). It matches vo_return_spread within 2–11%, pw_xsec's transition shape within 0.007 and pw_eddy within 0.3 points [C].
- **Closed forms** (worst L′ error, 10 kHz–10 MHz) [C]:

  | Model | Trace over its return | Pair over a floating plane |
  |---|---|---|
  | Perfect image (today's image PEEC) | 68% | 79% |
  | One complex image at h + p (Deri 1981 [S]) | 13% | 33% |
  | 4 / 6 rotated Gauss–Laguerre images | 0.8% / 0.5% | 3.5% / 0.4% |
  | 8 images, untuned | 0.8% | 2.4% |

  Tuned on these two cases, the 4- and 6-image sets are exact out of sample on pw_eddy's 3-D coil. Each term is an image at a complex depth, so existing PEEC formulas carry over ([DCIM](https://sharif.edu/~aborji/25120/files/A%20Direct%20Discrete%20Complex%20Image%20Method%20from%20the%20Closed-Form%20Greens%20Functions%20in%20Multilayered%20Media.PDF) [S]).
- **Thin-sheet Carson law.** For h ≪ ℓ_m ≪ W the plane's return resistance tends to ωμ0/4, about 2 mΩ/mm per MHz, whatever the copper weight (0.98–0.99 of it at 1 kHz) [C]. Thicker copper localizes the return but does not cut its loss.
- **The mirror window.** ℓ_m and λ/10 both scale as 1/f, with ratio πη0/(10√εr·R_s) ≈ 1.2×10⁵: a 10 mm structure is mirrored and lumped from 12 kHz to 1.45 GHz. A 1 oz plane holds a 5 mm loop's image for 6.4 µs.

### 4. Derivation C: decaps and stitching vias are one wire medium

For a plane pair, Z_s = 2R_s + jωμ0d per square and Y_p = jωC′ + n/Z_post. With inductive posts this gives γ² = (ω_p² − ω²)/v², ω_p² = n/(L_post·C′):

| Band | Physics | Round-1 result contained |
|---|---|---|
| Below SRF | γ² < 0: slow wave | "Location doesn't matter" |
| SRF to f_p | Screening, λ = v/√(ω_p² − ω²) → √(L_c/(μ0dn)) | XD113 reach; Belov cut-off |
| At f_p | λ → ∞, the k = 0 mode | Lumped anti-resonance |
| Above f_p | Modes at √(f_mn² + f_p²) | Posts raise cavity modes |

Lattice checks [C]:
- **Screening.** Decap share curves match 1 − γR·K1(γR) within 0.05 from 50 MHz to 1.5 GHz, as λ grows from 10.9 to 18.5 mm.
- **Anti-resonance.** 1898 MHz against f_p = 1898 MHz.
- **Board modes (60 mm).** 0.94 / 2.58 / 3.52 GHz against 0.94 / 2.59 / 3.54 predicted.
- **Stitching.** f_p within 0–2%, λ within 1–3%.
- **Point load.** L_in ≈ (μ0d/2π)·ln(1.12λ/r): 85 pH at d = 0.1 mm, 690 pH at 1 mm, with d ln L_in/d ln L_c = 0.07–0.17. Plane spacing is linear, ESL logarithmic. The continuum is within 1% at L_c/(μ0d) = 5.6 and 12–20% low at 0.56.

On RB4, 10 mm stitching gives f_p = 3.39 GHz; ≤ 12 mm keeps the GND/GND cavity screened at 2.45 GHz.

### 5. Scales of a board (RB4: 60 × 40 mm, 4 layers, 0.1 mm prepreg, 0.5 oz planes) [C]

| Length | Value | Time | Value |
|---|---|---|---|
| δ at 2.45 GHz | 1.3 µm | ε0/σ_Cu | 1.5×10⁻¹⁹ s |
| plane copper (δ = t at 14 MHz) | 17.5 µm | transit across h / board | 0.7 ps / 0.42 ns |
| prepreg h; ℓ_m at 500 kHz | 0.1; 0.50 mm | edges; ring period | 35 ps–2 ns; 6 ns |
| via-row L_T | 1.1 mm | image hold, h / 4 mm loop / board | 64 ns / 2.6 µs / 38 µs |
| v·t_r/6, 100 ps / 1 ns | 2.4 / 24 mm | switching period | 2 µs |
| 1/k_p, 10 mm stitching | 6.8 mm | surface τ_e, humid residue / clean (assumed σ_s) | 23 µs / 2.4 s |
| Chu radius, 2.4 GHz | 7.5 mm | thermal: 0.1 mm FR-4 / 10 mm Cu | 67 ms / 0.9 s |
| ℓ_m at 20 kHz | 12 mm | FR-4 bulk τ_e (10¹² Ω·m, assumed) | 38 s |
| decap reach, 10 mm pitch | 24 mm | board thermal; CAF test | 160 s; 500 h |
| thermal λ; λ_d/2 at 1 GHz | 46; 72 mm | | |
| loss length (100 / 35 ps); λ/2π at 30 MHz; ℓ_m at 50 Hz | 235 / 82 mm; 1.6 m; 5 m | | |

### 6. Regime map and causality [C]

| RB4 structure | Small parameters | Representation |
|---|---|---|
| Hot loop, 12 V/10 A, 2 ns | θ 0.058, Z0/Z 6.7, ε_L 0.39, Q 30–170 | ε_L·Q ≫ 1: co-simulate L with C_oss |
| Its 500 kHz return in L2 | 2h/ℓ_m 0.40, a/ℓ_m 8 | Complex images |
| SPI clock, 1 ns, 30 mm, 30 Ω driver | θ 0.40, ε_C 0.71 | Order 2: line plus load ring |
| USB 2.0 HS, matched | θ 0.67, Z0/Z 1 | Delay and balance only |
| PDN, 0.1 mm L3–L4 | Z0/Z 1.2, L_c/(μ0d) 5.6 | Wire medium |
| ESD, 30 A/0.8 ns, 10 V clamp | ωL/Z_clamp 0.25 (via to L2), 11 (to L4) | > 1: parasitic is the circuit; L ≤ 0.12 nH |
| 24-bit ADC, DC–10 Hz | S/B 8.4×10⁶ | Orders 1–4: sheet R, ∇T, Seebeck, leakage |
| 1 m cable; 2.45 GHz antenna | resonant sizes | Antennas: MREMC chain; F3 |

**Critical length.** Largest T_d/t_r for an overshoot budget (lossless line, ramp drive):

| R_s/Z0 | 5% | 10% | 20% | Overshoot at t_r/6, t_r/2 |
|---|---|---|---|---|
| 0.1 | 0.02–0.04 | 0.06–0.08 | 0.10–0.22 | 8–46%, 83% |
| 0.3 | 0.06 | 0.10–0.18 | 0.16–0.24 | 10–24%, 47–52% |
| 0.6 | 0.14–0.18 | 0.24–0.28 | 0.44–0.56 | 5–6%, 19–24% |
| 1.0 | ∞ | ∞ | ∞ | 0, 0 |

t_r/6 (Johnson) is a ~10% budget with typical drivers; t_r/2 (LearnEMC) is ≥20% with weak ones.

**Kramers–Kronig.** A causal wideband-Debye FR-4 fitted at 1 GHz (Dk 4.3, Df 0.02; Djordjevic et al. 2001 [S]) gives Dk 4.68 at 1 MHz and 4.17 at 10 GHz. That is −2.93% per decade, equal to −(2/π)·tanδ·ln 10. Between 1 MHz and 5 GHz, stripline Z0 moves +5.4% and delay −5.1%. Beyond the loss length c·t_r/(3.08√εr·tanδ), a line sets its own edge.

### 7. Derivation map

| Rule or result | Principle |
|---|---|
| "δ > t, so the plane cannot shield" is wrong | P3: ℓ_m = δ²/t ≪ δ |
| Star ground vs plane (RG19, PW21, P45 vs S39) | P3: the victim band vs f(ℓ_m = W), f(ℓ_m = 2h) |
| Area → height × squares (PW25, LA26) | P2, P3: L = Σ Z0·T_d while ℓ_m < a |
| 3W is 60× apart in microstrip vs stripline | P5: (h/D)² vs e^{−πD/b} |
| Corners matter only for pulses under 1 ms; I²t | P7: √(αt) vs feature |
| Via fields conduct at edges (XD22) | P7: L_T/p ≈ 0.4–1, so no homogenization |
| Spreading parts futile below 2λ (TM1); electro-thermal fixed point (TM16) | P5 saturation; P7 averaging |
| Topology beats tweaks by 20–40 dB | P5: far fields see low-order moments [I] |

### 8. Convergences and synergies round 1 missed

- **One dispersion law, four workstreams.** Decap reach (XD), stitching cut-off (FE), the anti-resonance (rules) and post-raised modes are one law. f_p becomes one knob for the frequency plan (S8, DR36).
- **One length, five findings.** f_x, PW24, RG19, PW21's 0.39 → 0.068 nH/mm and the slot-law switch (XD2 vs FE) are each ℓ_m against a scale. A 20 mm slot turns inductive above ≈ 6 kHz [I].
- **One diffusion test.** Pulse corners, I²t fusing, image hold times and transient heat ([lens-th](lens-th.md)) all compare a diffusion length with the feature size.
- **One reason early decisions win.** Topology over tweaks, area over shape, length over width: the leading scale dominates.
- **One selector.** RG2's 14 groups, SIM4 and the band table reduce to θ, Z/Z0, ℓ_m/ℓ and ωτ_e, plus budget scaling.

### 9. Transfers

| From | To |
|---|---|
| Wire-medium metamaterials | Decap and stitching design by f_p (LS8, LS9) |
| Earth-return complex images; Carson's ωμ0/8 | Transition-band plane returns (LS1, LS4) |
| Microwave matching | Power and high-Z analog through Z/Z0 (LS5) |
| HV grading by ωτ_e | Humid creepage, guards (LS18) |
| SI causal fitting | Coupon calibration; TM35 tolerances (LS16) |
| Homogenization, multigrid, two-timescale SA | Optimizer levels, JPR50 step ratios (LS22–LS27) |

### 10. What each conductor is doing, across scales

A conductor's job depends on the frequency and on the length scale of the question. Its own dimensions set the switch points: mirror at R_s/(πμ0a), localized return at R_s/(2πμ0h), skin at ρ/(πμ0t²), line at v/(10ℓ), resonance at v/(2ℓ), and radiation growing as (ka)³.

| Conductor | Low f | Transition | Middle band | High f |
|---|---|---|---|---|
| L2 GND plane | resistive return, heat spreader | receding image; return width ≈ 2h + ℓ_m | mirror at trace scale, antenna arm at cable scale (same f) | cavity wall above f_p |
| Stitching via | 1 mΩ | — | (μ0t/π)·ln(s/r) | plasma post; launch ∝ (ks)² |
| Decap + mount | capacitor (slow wave) | resistor at SRF | screening post | k = 0 partner at f_p |
| 1 m cable | return | — | antenna, 30–300 MHz | — |

[lens-cd](lens-cd.md)'s passport should therefore hold job(f, ℓ), evaluated at each budget's observable scale (LS28, LS29).

### 11. Critique of round 1's synthesis

| Claim | Problem | Restatement |
|---|---|---|
| Synthesis object #1, "screened Laplace on sheets" | Only real γ²; eigenmodes (#6) are the same operator; magnetic sheets are non-local | One complex-γ² operator plus the \|k\| kernel |
| "Decap reach 4–24 mm" (principle 4) | Holds only from SRF to f_p; diverges at the anti-resonance | λ(f) = v/√(ω_p² − ω²) |
| f_x as one boundary; gap 2 "the hardest regime" ([gaps](research-gaps.md)) | One point of a band; intact planes have a closed form | Gap 2 = slotted, perforated, finite planes |
| Principles 2–3 | No impedance level; "height is the strongest knob" in one direction only | Move Z0 toward Z; length sets θ² |
| Fixed band table (design-reasoning) | Edges are scale ratios | ℓ–f regime plane; Regime gets a scale (LA11) |
| Fidelity ladder (principle 11) | Series diverge at ε·Q ≥ 1; fidelity won't fix it | Switch representation; error = first neglected term |
| Basis set | No causality and no ωτ_e | Causal stackup model; τ_e in Ins |
| Principle 14, DR42 | Below f(ℓ_m = cell), no layout closes current in a cell | Locality per band; DC isolation by topology ([lens-ct](lens-ct.md)) |
| JPR three timescales | Compute schedules, not physics scales | Order by spatial scale, then τ |

## Recommendations for our system

1. **Give each structure θ, Z/Z0, ε_L and ε_C per band.** At ε·Q ≥ 1, switch to co-simulation or modes (LS5, LS15).
2. **Put 4–6 complex images into the PEEC core (SIM16, SIM46).** Mesh only slots and edges (LS1–LS4).
3. **One wire-medium module** for reach, anti-resonance and mode shifts; f_p becomes a plan variable (LS8–LS11).
4. **The ℓ–f regime plane as regime selector,** with truncation σ and n* (LS12–LS14).
5. **A causal stackup model, a loss-length gate, surface τ_e** (LS16–LS19).
6. **Placer kernels by decay class,** mode-shape coordinates above cut-off, scale-ordered decisions (LS20–LS27).
7. **Add ℓ_m and f_p coupons** to the calibration panel (LS30, LS31).

## Conflicts and open questions

- **Complex images.** They are checked only on infinite, intact, thin planes (2-D and axisymmetric 3-D), and the (φ, β) parameters were tuned on two cases.
- **Lattice checks are model against model,** with lumped posts.
- **The RB4 design points, S/B values and σ_s ranges are illustrative** [I]. n* assumes geometric hierarchies.
- **The critical-length family** uses a capacitive load and a lossless line; clamps and losses shift it.
- **Notation across lenses.** [lens-sy](lens-sy.md)'s ℓ_d is ℓ_m/2. [lens-ct](lens-ct.md)'s K_C and K_L equal ε_C and ε_L with Z0 eliminated.

## Sources

- Haus & Melcher, *Electromagnetic Fields and Energy*, §3.3 ([MIT OCW](https://ocw.mit.edu/courses/res-6-001-electromagnetic-fields-and-energy-spring-2008/pages/chapter-3/)) [S].
- Liu & Belcher, [arXiv 0712.0182](https://arxiv.org/abs/0712.0182), eq. (1) [P]; Saslow, Am. J. Phys. 60:693 (1992) [S].
- Djordjevic et al., IEEE T-EMC 43(4):662 (2001) [S]; Deri et al., IEEE T-PAS 100 (1981) [S].
- Belov wire medium via [fields-si-emi](fields-si-emi.md) [S]; Dodd–Deeds via [pw_eddy.py](../../../tools/research/physics/pw_eddy.py) [S].
- Scripts: [ls_thin_sheet.py](../../../tools/research/physics/ls_thin_sheet.py) (reuses pw_eddy and pw_xsec), [ls_post_lattice.py](../../../tools/research/physics/ls_post_lattice.py) (extends xd_lengths), [ls_regime_map.py](../../../tools/research/physics/ls_regime_map.py).

See also: [README](README.md) · [cross-workstream-synthesis](cross-workstream-synthesis.md) · [research-gaps](research-gaps.md) · [lens-vp](lens-vp.md) · [lens-ct](lens-ct.md) · [lens-sy](lens-sy.md) · [lens-th](lens-th.md) · [lens-in](lens-in.md) · [lens-cd](lens-cd.md) · [lens-ls ideas](../../ideas/physics-first/lens-ls.md)
