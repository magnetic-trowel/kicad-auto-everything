# Fields view of SI and EMI: return paths, crosstalk, cavities, pairs

*Tags: [P] primary source read, [S] snippet or secondary, [V] vendor claim, [I] our inference, [C] computed by us (script named).*
*Scripts: [fe_peec_plane.py](../../../tools/research/physics/fe_peec_plane.py) (PEEC plane solver), [fe_field2d.py](../../../tools/research/physics/fe_field2d.py) (2-D field solver), [fe_cavity.py](../../../tools/research/physics/fe_cavity.py) (plane-pair cavity model), [fe_geometry.py](../../../tools/research/physics/fe_geometry.py) (closed forms).*

**TL;DR**
- **One quantity replaces about a dozen plane rules:** the extra impedance a fast net's return current meets, ΔZ_ret(f) (mostly jωΔL), times the net's current spectrum I(f). The product is a voltage that is charged to an SI budget (mV at the receiver) and an EMI budget (mV between cable attachment points). Slots, splits, merged antipads, reference changes, return-via distance, stitching caps, plane-edge offsets and "no fast nets between connectors" are all terms of it.
- **Sizes [C]:** a slot under a trace adds ΔL ≈ μ0·l / (2·ln(4l/g)), about 0.08–0.13 nH per mm of slot, and this barely depends on trace height. A return via at distance s adds only (μ0·t/π)·ln(s/r), about 0.1–0.3 nH. Its main job is to stop the via launching a wave into the plane pair. s ≈ λ_d/10 at Nyquist reproduces TI's 200 mil (5 Gb/s) and, within 30%, its 50 mil (Gen5).
- **Crosstalk is field overlap.** Microstrip coupling falls as ~(h/D)². Stripline coupling falls as exp(−πD/b), about −11 dB per extra h, and stripline FEXT is zero. At 3W, saturated NEXT is 1.3% in microstrip and 0.02% in stripline, so spacing must come from a per-victim noise budget, not "3W".
- **Plane pairs are cavities.** A stitching pattern has a computable first resonance. Square grids follow the wire-medium cut-off within 3–16%. A grid beats random vias of the same count by up to 2.2×. Perimeter-only stitching raises the first mode only ~1.5×. "Largest empty circle" predicts the first mode within about ±30%; the cavity eigenvalue takes seconds.
- **Differential pairs:** tighter coupling lowers emission only while k·s exceeds the driver imbalance ε, so it stops helping below s* = ελ/2π (0.5 mm at 1 GHz and 1%, which is Johnson's number). At 100 Ω, loose coupling allows ~55% wider traces (about 30% less conductor loss). Skew converts to common mode as |sin(πfΔt)|/2.

## Key facts

### 1. Where return current flows

| Structure | Plane current density | Spread |
|---|---|---|
| Microstrip, height h | K(x) = (I/π)·h/(h²+x²) | within ±1h / ±3h / ±10h / ±20h: 50 / 80 / 94 / 97% = (2/π)·atan(x/h) [I]. PEEC with w = 2h: 51 / 78 / 94% [C fe_peec_plane] |
| Stripline, trace at h1 in a cavity of height b | ∝ sin(πh1/b) / (cosh(πx/b) − cos(πh1/b)) (conformal map) [I] | tails fall as exp(−π\|x\|/b); share on the nearer plane = 1 − h1/b (75% for h1 = b/4, matching Adamczyk [S]) |

- **Correction to [si-fundamentals](../rules/si-fundamentals.md):** it says "97% within ±10h". Adamczyk's 97% is for 200 mil either side of a trace 10 mil up, i.e. ±20h ([In Compliance](https://incompliancemag.com/pcb-return-current-distribution-in-a-microstrip-line/) [S]). The filament formula gives 94% at ±10h.
- **Validation of our PEEC:** loop inductance of a w = 2h microstrip is 0.302 nH/mm, against 0.298 nH/mm from the closed form Z0_air/c [C].

### 2. Discontinuities as extra return impedance

| Feature | Physics and closed form | Size [C] | Consequence |
|---|---|---|---|
| Slot under the trace (length l, width g) | The return detours along both slot edges: two shorted slotline stubs, ΔL ≈ μ0·l / (2·ln(4l/g)) | PEEC at h = 0.2 mm: 5 × 0.1 mm → 0.39 nH; 10 × 0.1 → 0.79; 10 × 0.4 → 1.28; 20 × 0.4 → 2.34 nH. Within 18% of the formula for l ≥ 25h, g ≥ 2h; the formula overestimates short or narrow slots up to 2× | Linear in length, logarithmic in width, nearly independent of h, so a thinner dielectric does not fix a slot. 2.3 nH ≈ 8 mm of extra 50 Ω trace; reflection L/(2·Z0·t_r) ≈ 23% at 100 ps |
| Ott's slot measurement (10 MHz, 3 ns) | plane voltage over 1": 15 mV, then 20 / 26 / 49 / 75 mV for ¼ / ½ / 1 / 1.5" slots; 15 separate holes: 15 mV ([Ott](https://hott.shielddigitaldesign.com/techtips/tips-slots.html) [P]) | Same order as PEEC; Ott's growth is a little steeper than ours (method not stated) | Separate holes shorter than a few h add < 0.3·h nH each: they don't matter. Merged antipads are one slot |
| Split plane (slot reaches an edge, bridge far away) | Whole slot voltage appears between the halves | EMI case B2: 14 dB worse than an interior slot ([fields-emi-budget](fields-emi-budget.md)) | Never split under fast nets; a bridge is a single forced crossing |
| Same-net reference change, return via at s | Radial waveguide: Z_pair = (ωμt/2)·[H0(ka) − H0(ks)]. Im → (μ0·t/π)·ln(s/r). Re → power launched into the plane pair, relative to an unpaired via: 1 − J0(ks) | t = 0.2 mm, r = 0.15 mm: 97 / 174 / 292 pH at s = 0.5 / 1.3 / 5 mm. Cavity launch is −10 dB at ks = 0.63: s = 5.8 / 3.6 / 1.8 / 0.9 mm at 2.5 / 4 / 8 / 16 GHz [C fe_geometry F] | The inductance is logarithmic in s, so distance mostly controls cavity excitation (crosstalk to every other via, edge radiation), which grows as (ks)². "s ≤ λ_d/10 at Nyquist" decompresses TI's 200 mil and 50 mil rules ([si-fundamentals](../rules/si-fundamentals.md)) |
| Different-net (P↔G) reference change | The return must use a decap (ESL plus mounting ~1–2 nH; Ott 5–10 nH with traces [P]) or displacement current into the cavity | At 1 GHz a 1.5 nH cap path is 9.4 Ω, more than the cavity's local impedance (order 1 Ω for t = 0.2 mm [I]) | The current goes into the cavity. Ott's "interplane capacitance helps only above ~500 MHz" is right, and that same wave excites cavity modes |
| Trace near a plane edge | SI: Z0 rises only within ~3h. EMI: return flux wraps the edge and raises the net plane inductance between board ends | PEEC, trace 3h from the edge: V between board ends ×2.7 (end-centre cable points) to ×6.9 (corners on the trace side) vs centred; MREMC formula ×4.3 [C] | There is no threshold: the EMI effect follows roughly 1/√d (MREMC). 2h, 3h and 90 mil are points on one curve |

### 3. The one metric: return-path EMF
For each fast net n with current spectrum I_n(f) (from t_r, swing and load):

V_ret,n(f) = I_n(f) · Σ_k ΔZ_k(f),  ΔZ_k = jωΔL_k + R_cav,k

It has two projections:
- **SI:** the part that appears at the receiver: ground bounce, reflection and shared-return crosstalk, compared with a noise budget in mV.
- **EMI:** the part that appears between cable attachment points a and b, V_ab(f) = I_n(f)·Z_ab,n(f), where Z_ab,n = jω·(L_net,ab + Σ κ_ab,k·ΔL_k). It is weighted by the antenna transfer and the limit to give a margin in dB ([fields-emi-budget](fields-emi-budget.md)).

| Rule of thumb | Term of the metric it approximates |
|---|---|
| Don't cross splits or slots; merge antipads into voids | ΔL_slot with l = slot or antipad-cluster length |
| Return via within 200 mil, scaled by data rate | (μ0t/π)·ln(s/r) and cavity launch 1 − J0(ks) |
| Stitching caps ≤ 1 µF at unavoidable crossings | A shunt across ΔZ_slot; it buys ~10 dB above its SRF (EMI case C) |
| Avoid power-plane references and P↔G changes | Decap path plus cavity term |
| ≥ 2h / 3h / 90 mil from plane edges | Edge enhancement of L_net (smooth, ~1/√d) |
| No fast circuitry between connectors; cabled connectors on one edge | κ_ab: ≥ 40 dB less plane voltage when both cable points are on one edge (PEEC) |
| Ott's layer-change order 1→4 | Ranking of ΔZ by transition type |
| No ground fill on multilayer boards | No term: fill adds no return path beside a plane |
| Slow edges first; series termination | I_n(f) |
| Bury fast nets in stripline (for EMI) | L_net between cable points ≈ 0 ("stripline induces nothing", LearnEMC [P]) |
| "Minimise loop area" | Replaced: LearnEMC notes radiation is not proportional to loop area ([P](https://learnemc.com/the-most-important-emc-design-guidelines)); what matters is the voltage between antenna parts |

Each term is a microsecond closed form. Only κ_ab (the share of a local return voltage that reaches a pair of cable points) needs a field solve: seconds of PEEC per outline and connector pair.

### 4. Crosstalk from field overlap
2-D field solve [C fe_field2d]. Microstrip: h = 0.1 mm, w = 0.19 mm, εr 4.3, 49 Ω (Hammerstad-Jensen gives 48 Ω). Stripline: b = 0.235 mm, w = 0.06 mm, 54 Ω. D is centre-to-centre spacing; h is the distance to the nearest plane.

| D/h | Microstrip K_L | K_C | NEXT_sat (K_L+K_C)/4 | FEXT coeff. (K_L−K_C)/2 | Stripline NEXT_sat | Johnson 1/(1+(D/h)²) |
|---|---|---|---|---|---|---|
| 2 | 0.454 | 0.304 | 18.9% | 7.5% | 4.0% | 20% |
| 3 | 0.179 | 0.081 | 6.5% | 4.9% | 1.06% | 10% |
| 4 | 0.100 | 0.033 | 3.3% | 3.3% | 0.28% | 5.9% |
| 6 | 0.043 | 0.010 | 1.3% | 1.6% | 0.02% | 2.7% |
| 10 | 0.013 | 0.003 | 0.4% | 0.5% | ~0 | 1.0% |

- **Johnson's formula** bounds saturated NEXT about 2× conservatively for D ≥ 4h, but K_L alone exceeds it. Use it as a NEXT bound, not as a coupling coefficient.
- **Microstrip FEXT** = coefficient × (coupled delay / t_r). At D = 4h, 50 mm coupled (≈300 ps) and t_r = 100 ps it is ~10%, larger than NEXT. Long parallel microstrip runs are FEXT-limited. Stripline FEXT is zero (homogeneous dielectric).
- **Stripline decays about ×0.27 per extra h.** Stripline at D = 4h matches microstrip at D ≈ 12h.
- **3W** (D ≈ 5.9h here): 1.3% NEXT in microstrip, 0.02% in stripline. So the slogan is 60× too strict in stripline and can be too loose for long microstrip runs.
- **Ground pour on the same layer** at gap ≥ 2h changes Z0 by < 2%; at 1h by −6.5%; at 0.5h by −16% [C]. Johnson's "ground fill modulates Z0" ([P](https://www.sigcon.com/Pubs/edn/GroundFill.htm)) applies only within ~2h.
- **Guard traces** sit where the field is already weak; a little more spacing does the same job ([myths](../rules/myths-and-contested.md)).

### 5. The board as resonant structures
Cavity model [C fe_cavity]: a 40 × 30 mm GND–GND pair, 0.2 mm apart, εr 4.3, via radius 0.15 mm, open (PMC) edges, losses tanδ 0.02 plus copper. Stitching vias are shorted ports.

| Stitching pattern | Vias | First resonance (GHz) | Largest empty circle D (mm, mirrored edges) | Belov cut-off f_p (GHz) |
|---|---|---|---|---|
| None (open board; TM10 = 1.81) | 0 | 1.80 | ∞ | — |
| Perimeter ring, 5 mm pitch | 26 | 2.80 (PEC-walled TM11 = 3.01) | 29.4 | — |
| Grid 10 / 7.5 / 5 mm | 12 / 20 / 48 | 3.3 / 4.0 / 7.45 | 14.1 / 14.6 / 7.1 | 3.39 / 4.77 / 7.78 |
| Perimeter + 10 mm grid | 38 | 4.3 | 14.1 | — |
| Random, 2 seeds each | 12 / 28 / 48 | 1.65–2.3 / 3.1–3.95 / 3.35–5.0 | 27–51 / 22–24 / 19–24 | — |

- **Wire-medium cut-off.** For a square lattice of pitch a: k_p²a² = 2π / (ln(a/2πr) + 0.5275) (Belov et al.; [arXiv 2505.17900](https://arxiv.org/abs/2505.17900) [S]). Below f_p the parallel-plate mode is cut off: the pitch at cut-off is ≈ 0.27 λ_d, and well below cut-off each pitch attenuates ≈ 1.7 Np ≈ 15 dB [I]. Agreement with the cavity model is 3% and 4% for the 10 and 5 mm grids, and 16% for 7.5 mm, where the board edge truncates the lattice.
- **Regular beats random:** at 48 vias, the grid's first mode is 7.45 GHz against 3.35–5.0 GHz for random placement. Stitching should be a lattice or blue-noise pattern, not "wherever there is room".
- **Largest-empty-circle (checker G).** The fit f ≈ κ·c/(D·√εr) gives κ = 0.49 ± 0.10 over 11 patterns, so the existing c/(2D√εr) is right on average, ±30%. It is biased low for grids (κ 0.32–0.40) and high for random patterns (0.43–0.64), and it ignores via radius and where the sources are. Use it as a screen and compute the eigenvalue for decisions.
- **Perimeter vs distributed is reconciled.** A perimeter ring leaves the interior resonant, only ~1.5× higher, as Hubing warns. It does suppress fringing at the edge, which is Ott's G/S/S/G concern. The two are optimising different outputs (internal coupling vs edge radiation).
- **Fences.** The infinite-plate formula for one row of posts is |T| = 2/√(4 + B²), with B = λ_d / (s·ln(s/2πr)) (inductive-post grating [I]). It gives −19 dB at s = λ_d/20 and −9 dB at λ_d/10. In a finite resonant board the realised isolation scattered from +3 to −33 dB around it [C], because a fence also creates two new cavities. Check fences with the cavity model.
- **GND–PWR pairs** (no shorting vias): f_mn = (c/2√εr)·√((m/a)² + (n/b)²) for the outline, independent of spacing ([LearnEMC](https://learnemc.com/ext/calculators/cavity_resonance/pcb-res.html) [P]). Decaps (≥ 1 nH) cannot short them above a few hundred MHz. Loss (tanδ, conductor) sets the peak height.
- **Slots resonate** as half-wave antennas: a 20 mm slot in FR-4 near 4.6 GHz (ε_eff ≈ 2.65) [I].

### 6. Differential pairs
- **Each leg returns under itself.** Coupling K_L is 0.24 at s = 1h and 0.014 at 8h [C]. At typical gaps, a pair is two single-ended lines that happen to be close ([Johnson](https://www.sigcon.com/Pubs/edn/ReturnCurrentMatters.htm) [P]).
- **Width needed for 100 Ω** (h = 0.1 mm) [C]:

  | Gap s | Width w | Zcomm | Relative conductor loss (∝ 1/(w+t)) |
  |---|---|---|---|
  | 1h | 0.112 mm | 37.5 Ω | 1.43 |
  | 2h | 0.150 mm | 28.6 Ω | 1.13 |
  | 4h | 0.163 mm | 26.2 Ω | 1.06 |
  | 8h | 0.175 mm | 24.7 Ω | 1.00 |

- **Emission crossover.** A pair's net magnetic dipole cancels. What is left is a quadrupole, about k·s times the single-ended emission, while imbalance ε (driver mismatch, skew, asymmetric surroundings) leaves ε times single-ended. Tightening helps only while k·s > ε, so s* = ε·λ/2π: 0.48 mm at 1 GHz and ε = 1%, 0.05 mm at 0.1% [C fe_geometry E]. This derives Johnson's "0.5 mm is close enough" ([P](https://www.sigcon.com/Pubs/edn/ReducingEMI.htm)).
- **Skew → common mode:** |V_cm/V_dm| = |sin(πfΔt)|/2. 5 ps at 2.5 GHz gives 2% (−34 dB); 20 ps gives 7.8% (−22 dB). In the time domain the peak is Δt/(2t_r) (Johnson).
- **What tight coupling really buys:** consistency and density. An aggressor couples nearly equally into both legs, arriving as common mode that the receiver rejects. Skew per bend shrinks with pitch: 2.8 ps per 90° arc turn at 0.3 mm pitch. Loose coupling is fine, and lowers loss, when each leg has solid reference and the skew budget holds.

### 7. Closed form, cheap numerics, or full-wave?

| Mechanism | Accurate closed form? | Cheap numerics (seconds) | Needs full-wave when |
|---|---|---|---|
| Z0, coupling, NEXT/FEXT of uniform lines | Yes (±5%) | 2-D FD/BEM per stackup | Never, for uniform lines |
| Slot, edge, net plane inductance | Slotline ±2×; MREMC ±2× | PEEC | Slot or board approaches λ/4 |
| Return via, reference change | Hankel radial model | Cavity model | Dense via fields above ~10 GHz |
| Plane-pair resonance with stitching | f_mn, Belov f_p | Cavity model with shorted ports | Irregular outlines (2-D FEM), radiation Q |
| Corners, pads, stubs | Yes ([rf-geometry](rf-geometry.md)) | 2-D FD for pads | 3-D via transitions above ~15–20 GHz |
| Cable common-mode emission | MREMC bound (±10–20 dB) | PEEC for κ | Enclosure and cable harness (still ±6 dB) |
| Antennas, near-field keep-outs | Chu bound only | — | Always (openEMS), then measure |

## Recommendations for our system
1. **Implement the return-path EMF ledger.** For each fast net, list its discontinuities with closed-form ΔL and cavity terms, then charge I1 budgets ([intent-and-why](../../ideas/original/intent-and-why.md)). It gives [R2 shadow return nets](../../ideas/original/routing.md) a physical cost of ω·ΔL·I instead of "forbidden".
2. **Compute κ_ab once per outline and connector set** with PEEC, as a map from return position to cable-pair voltage. The placer ([P8](../../ideas/original/placement.md)) then reads V_cm for any trace position in O(1).
3. **Replace the checker-G pass rule** c/(2√εr·d_max) > f_knee with the cavity-model first resonance. Generate stitching as a lattice with pitch from f_p > f_target.
4. **Crosstalk checker E:** use layer-type kernels (microstrip algebraic plus a FEXT term ∝ coupled length; stripline exponential) with coefficients field-solved once per stackup ([fe_field2d.py](../../../tools/research/physics/fe_field2d.py)).
5. **Return-via default:** s ≤ 0.63/k(f_Nyquist) ≈ λ_d/10, as a budget item, auto-placed in escape ([R3](../../ideas/original/routing.md)).
6. **Choose pair coupling** from loss, density and skew, not from EMI. Budget skew from the common-mode spec through sin(πfΔt)/2.

## Conflicts and open questions
- The "97% within ±10h" figure in [si-fundamentals](../rules/si-fundamentals.md) should read ±20h.
- PEEC here is quasi-static (no radiation, valid while slots are < λ/4), with zero-thickness planes. The ΔL formula should be checked against openEMS for 2–3 geometries.
- Ott's slot data grow faster with length than our ΔL. His probe method is not stated.
- The cavity model has open (PMC) edges and no radiation loss, so it overstates resonance Q. Edge-radiation claims (the Ott side of the stitching debate) need full-wave checks.
- Fence isolation in finite boards scatters widely around the closed form, so no simple pitch rule is safe for compartments.

## Sources
- Research notes: [rules_highspeed_emi.md § 1, 5–7, 9, 11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md); [verification_rules.md § 1A, 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- Ott tech tips: slots, stack-up 6 (https://hott.shielddigitaldesign.com/techtips/)
- Johnson, EDN columns (https://www.sigcon.com/Pubs/edn/)
- LearnEMC guidelines and cavity calculator (https://learnemc.com/)
- Adamczyk, return-current distribution (https://incompliancemag.com/pcb-return-current-distribution-in-a-microstrip-line/) [S]
- Belov et al., wire-medium plasma frequency, via [arXiv 2505.17900](https://arxiv.org/abs/2505.17900) and [cond-mat/0211204](https://arxiv.org/abs/cond-mat/0211204) [S]
- Cavity model: Lei, Techentin and Gilbert, IEEE T-MTT 47(5), 1999 [S]

See also: [fields-emi-budget](fields-emi-budget.md), [rf-geometry](rf-geometry.md), [si-fundamentals](../rules/si-fundamentals.md), [emc-placement](../rules/emc-placement.md), [checkers-si-emi](../rules/checkers-si-emi.md), [solver-ladder](solver-ladder.md), [ideas: si-emi-rf](../../ideas/physics-first/si-emi-rf.md)
