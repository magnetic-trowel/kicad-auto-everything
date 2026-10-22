# Derivation audit: which rules of thumb follow from first principles

**TL;DR**
- **132 of 160 rules (83%) derive from first principles, but only 51 cleanly; 81 need a stated regime condition.** Of the rest, 9 are conventions, 5 legal tables and 12 wrong habits. Only 2 cannot be derived: a material law and undisclosed vendor margins.
- **Rules derive; their numbers mostly do not.** Of 67 stated numbers, 12 derive, 23 are a budget evaluated at one regime, 14 are data and 18 are arbitrary. Locality and scales (θ, Z/Z0, ℓ_m, decay lengths) appears in 46% of the derivations: it turns a slogan into a rule.
- **Failure rules require principle D, extremes and accumulation (code P7).** Breakdown, fracture, fatigue and ageing follow local maxima and accumulated rates, not energies. Thomson's principle bounds a corner's loss, not its damage, so corner, teardrop and fatigue rules derive only with P7. Twelve rules need it.
- **Several rules hold for a different reason than the one usually given.** Switch-node copper is a board–world charge rule, Kelvin taps a reciprocity rule, snubbers designed loss. Impedance level (T1, Z0 → ΔV/ΔI) derives 18 rules, all self terms and no couplings.
- **Several widespread rules are wrong outside a narrow regime** [C]. A body-sized cut-out under an inductor is worse than keeping or clearing the plane. Reliefs do nothing physical in reflow. Stitching pitch follows the isolation distance, not λ/20. Guards help only on thick boards. Star grounds pay only from DC to a few kHz at board scale.

Tags: [S] secondary, [I] inference, [C] computed by [da_derivations.py](../../../tools/research/physics/da_derivations.py) (§A–§H), [da_inductor_cutout.py](../../../tools/research/physics/da_inductor_cutout.py) or [da_coverage.py](../../../tools/research/physics/da_coverage.py). The coverage script parses [derivation-audit-table](derivation-audit-table.md), one row per rule. Other numbers are quoted from the genealogy docs and the lenses cited inline.

## Key facts

### 1. Method

**Scope.** The audit covers the 160 rules of the three genealogy docs ([P01–P59](rule-genealogy-power-analog-thermal.md), [S01–S55](rule-genealogy-si-emi-rf.md), [R01–R46](rule-genealogy-routing-style-dfm.md)). Each rule got one attempted derivation, written as one line in the [table](derivation-audit-table.md).

**What counts as derived.** The line must yield the rule's direction (and its number, if any) from principles, geometry and material constants. It must also state the regime in which that holds.

| Code | Working principle | In [foundations](foundations.md) |
|---|---|---|
| P1 | Conservation: KCL/KVL, topology (cycles, cuts, articulation points, holes), the world node | F1; T5–T7 |
| P2 | Variational: Thomson, minimum magnetic energy, Foster, surface and elastic energy | F3; T4 |
| P3 | Reciprocity and symmetry: images, lead fields, mode conversion, gauge, wedge fields, apertures | F2, F4; T9 |
| P4 | Locality and scales: θ = ωℓ/v, Z/Z0, ℓ_m = R_s/(πμ0f), screening and decay lengths, ωτ_e | F5; T1, T8 |
| P5 | Dissipation and fluctuation: Q, noise, Wiedemann–Franz (WF), Joule heating | F6; T2, T10 |
| P6 | Information: margins, value of information (VOI), rules as compressed priors | F7; T13 |
| P7 | Extremes and accumulation (damage): principle D of the [README](README.md) | F6 damage clause; T11 |
| MP, LG, CG | Manufacturing process; legal and standards; cognition and tools | outer feasible set |

**Verdicts:**

| Verdict | Meaning |
|---|---|
| derivable | holds wherever the rule's object exists |
| derivable-with-regime | holds inside a stated regime only |
| convention | physically neutral choice |
| legal | a standard sets the number |
| habit-wrong | the derivation contradicts the rule |
| not derivable | the principles cannot produce it |

**Numbers** are classed derived, instance, data or arbitrary.

### 2. Coverage [C da_coverage]

| Verdict | Rules | Share | Examples |
|---|---|---|---|
| derivable | 51 | 32% | Kelvin taps, TVS at the connector, cables on one edge, annular ring |
| derivable-with-regime | 81 | 51% | 3W, decap distance, guard traces, thermal reliefs |
| convention | 9 | 6% | 45° routing, layer direction bias, placement order |
| legal | 5 | 3% | creepage, clearance, IPC-2221B spacing, creepage slots, spread spectrum |
| habit-wrong | 12 | 8% | three values per pin, 0.1 µF per pin, split AGND/DGND, 20-H, no 90° corners |
| not derivable | 2 | 1% | MLCC DC-bias derating (a material law), vendor skew tables (undisclosed margins) |

| Origin ([genealogy](rule-genealogy-power-analog-thermal.md)) | Rules | derivable | with regime | convention or legal | habit-wrong | not derivable |
|---|---|---|---|---|---|---|
| Physics | 91 | 41 | 49 | 0 | 0 | 1 |
| Simplicity proxy | 23 | 0 | 22 | 1 | 0 | 0 |
| Manufacturing | 16 | 10 | 5 | 1 | 0 | 0 |
| Habit or legacy | 15 | 0 | 3 | 0 | 11 | 1 |
| Cognition, tool, legal, contested | 15 | 0 | 2 | 12 | 1 | 0 |

| Principle use in the 132 derived rules | P4 | P2 | P3 | P1 | P5 | MP | P6 | P7 |
|---|---|---|---|---|---|---|---|---|
| Any mention | 61 (46%) | 49 (37%) | 49 (37%) | 37 (28%) | 26 (20%) | 23 (17%) | 9 (7%) | 7 (5%) |
| Primary | 24 | 30 | 22 | 23 | 13 | 16 | 3 | 1 |

What the counts say:
- **The physics corpus is sound but regime-bound:** 90 of 91 physics rules derive, 49 only with a regime; 102 rules need only P1–P6.
- **Simplicity proxies are one regime's budgets:** all but one derive, none cleanly ("3W", "2 mm", "200 mil", "λ/20").
- **Habits fail by variable:** 11 of 15 use the wrong one (pins, clock λ, signal width, area). Three hold narrowly: IPC-2221 (thermal only), guards (thick boards), hatching (flex).
- **Numbers are the weak part:** store budgets and compute numbers.

### 3. Nine short derivations

**D1. Three values per pin (habit-wrong).** Foster's reactance theorem is an energy statement. For a lossless one-port dX/dω = 4(W_m + W_e)/‖I‖² > 0, so the poles and zeros of X alternate. Two capacitors with different series resonances therefore force an anti-resonance between them, limited only by loss. 10 µF + 100 nF + 1 nF at 1 nH each peaks at 11 Ω near 130 MHz with 10 mΩ ESR; three 10 µF parts have no peak [C da §D]. The rule holds only where lead inductance scales with value (leaded parts). P2 and P5.

**D2. Guard traces (habit; regime-bound).** Over a plane, each trace and its image form a line dipole, so the field reaching mid-gap is already down by about (h/D)². A grounded guard removes only that remnant: −1–3% at h = 0.1 mm, −48% at h = 1.6 mm (D = 5 mm; [lens-sy](lens-sy.md) D1). Guards are a two-layer tool (h ≳ D/3). P3.

**D3. No 90° corners (myth).** A bend has two corners with dual physics. The inside (concave) corner crowds current, J ∝ r^(−1/3). The outside (convex) corner crowds field in a high-voltage gap, E ∝ r^(−1/3) [C da §H]. Loss, an energy, moves only 0.06 squares, and signal integrity sees the excess capacitance only above f·h ≈ 3 GHz·mm. Corners matter where the governing quantity is local: pulses shorter than w²/α (0.8 ms at w = 0.3 mm), fusing, HV and ESD. That needs P7, not P2.

**D4. Switch-node copper minimal (a world-charge rule, not a node-capacitance rule).** Charge conservation on a surface around the board gives I_CM = −jω·Σ C_i,ext·V_i ([lens-ct](lens-ct.md) D2). Only charge whose field ends outside the cell drives common mode, so capacitance to the node's own return plane is free. Over a plane the node is a vertical dipole ∝ ∫V dA, coupling ∝ h^0.19 (SY). The variable is outward area at voltage, and thinner prepreg does not help, unlike for loops. P1 and P3.

**D5. Kelvin taps (a reciprocity rule).** By reciprocity a sense port reads a source current density J through its lead field E_L: V = (1/I_L)∫J·E_L dV ([lens-sy](lens-sy.md) P1). The error vanishes when the taps sit on the load's equipotentials and the sense cycle shares no piece with the load ([lens-cd](lens-cd.md) D4). At AC a voltage belongs to a loop, so route the pair together and filter at the IC. The resistive picture is the DC case. P3.

**D6. Snubber at the switch pins (placement by objective).** For first-peak overshoot, L_s → 0 is right. For ring decay, emission and loss, a snubber is a tuned absorber (Den Hartog). Its branch impedance R_s + jZ0(l − 1/n) is resistive when L_s·C_s = L·C_oss. With C_s = C_oss and L_s ≈ L it reaches Q ≈ 1 at 72 mW, against 216 mW for C_s = 3·C_oss ([lens-th](lens-th.md) D3). The binding objective decides placement. P5.

**D7. Thermal reliefs (manufacturing).** Wiedemann–Franz makes a spoke's thermal and electrical resistance one number, R_el = ρk·R_th, so 37 K/W costs 0.25 mΩ [C da §A].
- **Hand or wave soldering:** the relief cuts the joint's drain 1.8–4.2×, which is its purpose.
- **Reflow:** a pad couples ~0.1 mW/K to the oven but 27–54 mW/K to the plane, so it follows the plane either way. Isolating it would take ≥ 10⁴ K/W, i.e. ≥ 66 mΩ.

P5, P4 and MP.

**D8. Stitch every λ/20 (proxy).** A 2-D via lattice is a wire medium: k_p² = 2π/(a²(ln(a/2πr) + 0.53)), with pitch a and via radius r, independent of plane spacing.
- **Below cut-off** the cavity field decays 11–19 dB per pitch at any frequency, so the pitch follows the isolation distance. Frequency enters only through f_p > f_max (a ≲ λ/4); λ/20 at 2.45 GHz gives f_p = 6.2·f_max [C da §B].
- **A single fence row** is an inductive grid leaking ≈ 2(a/λ)·ln(a/2πr): −19 dB at λ_g/20, −9 dB at λ_g/10.
- **Vias reflect; they do not damp** (TH).

P4, P2 and P5.

**D9. Three vendor numbers in one line each** [C da §A, §G]:

| Rule | Derivation | Result |
|---|---|---|
| PDN peak ≤ 1.57·Z_t | a load toggling at the resonance has fundamental (2/π)·ΔI | Z_pk ≤ (π/2)·Z_t |
| TI's ESD corner radius ≥ 2.6 mm | an isolated feature at 8 kV has surface field ≈ V/r; air breaks down at 3 kV/mm | r = V/E_bd = 2.7 mm (Peek: 1.5 mm) |
| ≥ 1 via per amp | an end-cooled barrel self-heats ΔT = V²/(8L0T) (Kohlrausch, from WF) | 1 A heats a 1.3 mΩ via by 0.03 K; 10 K takes ~18 A, so loop L or IR sets the count |

### 4. What does not derive, and principle D

**Not derivable (2).** MLCC DC-bias derating (P27) is a ferroelectric constitutive law, an F2 break in [foundations](foundations.md). Vendor skew tables (S29) encode undisclosed margins. Physics states the budget each replaces, not the number.

**Habit-wrong (12):** 11 habit rules plus 20-H, each with the wrong variable or an obsolete regime (leaded capacitors, immersion etching, clock-λ termination).

**Principle D (P7): extremes and accumulation is required.** Failure is governed by local maxima and accumulated damage, not by energy.
- Damage rates are steep: Arrhenius ageing doubles per 10 °C; Coffin–Manson fatigue is a power law; breakdown, yield and fracture are thresholds.
- They are local: they see corner singularities r^(π/α−1), so the governing quantity is a maximum or high-power norm, not a quadratic energy.
- Energy principles cannot stand in for it: Thomson's principle bounds a corner's loss effect at ≤ 0.3 squares and says nothing about pulses, HV, ESD or fatigue.

Twelve rules need P7: P47–P49, P52, P58, R01, R03, R18, R20, R30, R35, R39. Seven derive only with it, for example teardrops (stress at a re-entrant corner ∝ r^(−0.46) [C da §H]), the MLCC distance from a V-score and rounded pulse corners. Three are legal tables whose direction it explains.

In [foundations](foundations.md), P7 is F6's damage clause and T11. It needs its own objective class in the solver API (damage norms beside losses), and its rate laws are constitutive data, like ε and σ.

**Scope notes.**
- **Reciprocity fails in moving media.** "Electrolytics upstream" (P58) needs advection, one of F2's breaks.
- **Manufacturing physics is mostly P1–P6 in other fields,** plus process data. 22 of 24 process rules have such a core: surface energy (tombstoning, wicking: P2), elastic strain with Saint-Venant decay (V-score, warp: P2, P4), screened transport in a plated hole (aspect ratio: P4) and z-score margins (annular ring, DRC margin: P6).
- **Cost is an input the set lacks.** Via-in-pad and one-sided assembly need it ([research-gaps](research-gaps.md) gap 19).

**Impedance level (T1) derives 18 rules, all self terms.** Z0 → ΔV/ΔI gives hot loops, laminated buses, gate loops, plane pairs, TIA and feedback nodes, crystal nodes, 50 Ω lines, voided pads, necks and NFPs. It derives no coupling rule (3W, guards, switch-node area, connectors), as T1's self-term condition predicts.

### 5. Common rules and what governs them

| Rule | Verdict, regime and reason | Basis |
|---|---|---|
| P05 loop-area tiers | Self L follows h × squares (P2). Area × h is the image quadrupole moment, which sets far coupling and DM emission (P3). Use tiers for emission at fixed h, not overshoot | VP, CT D5, SY, IN |
| P11, P38, P45, S39 star and split grounds | They pay only where ℓ50 = R_s/(2πμ0f) exceeds the aggressor–victim distance: below 6 kHz at 10 mm on 1 oz [C da §C], far below the 100 kHz of the audio rule. A single tie is exact only as an articulation point; place it at the aggressor's stagnation point (leak ∝ w⁴, not w²) | VP D5, LS, CT D3, CD D3 |
| S17 guard traces | Only where h ≳ D/3, cutting coupling up to ~6 dB | SY D1 |
| S16 reduce h before spacing | Loops only; wide dv/dt copper couples ∝ h^0.19 | SY D1 |
| S15 3W | An accidental D/h rule (w/h ≈ 2 at 50 Ω); over-spaces stripline, where coupling decays as e^(−πD/b) | IN D3, LS |
| "As close as possible" (P02, P24, S35, S51) | Linear for series paths and node C (63 pH/mm at h 0.1, w 2 mm; 0.8–2 ppm/mm for crystals). Logarithmic for plane spreading (20 pH/mm at 2 mm on d = 0.1 mm), bounded by a screening length that diverges at f_p [C da §F] | LS, VP D3 |
| P16 snubber at the pins | By objective: overshoot → closest; ring Q and loss → tuned L_s·C_s ≈ L·C_oss | TH D3 |
| P13 copper under inductors (Rohm and TI disagree) | Keep the plane. A body-sized cut-out is a ring still carrying eddy current at its rim: loss 1.05–1.4×, shielding largely lost. Cut-outs ≥ 2–3× the winding radius cut loss and ΔL to 3–50% (0.5–2 MHz) but unshield lower layers [C da_inductor_cutout] | CT holes, LS ℓ_m, SY images |
| R25 thermal reliefs | Per process: hand, wave and THT soldering, yes. In reflow there is no physical effect; balance is set by what the pad is tied to | WF [C da §A]; WS7 |
| S37, S48, R24 stitching at λ/20 | 2-D lattice: pitch from the isolation distance, plus f_p > f_max. 1-D fence: −19 dB per row at λ_g/20. Damping needs edge resistors | LS, TH D4 [C da §B] |
| P41 driven guard (fA) | Removes leakage and effective C within the buffer's bandwidth; dielectric noise 4kT·ωC·tanδ survives | TH |
| P57 spread hot parts | No mean-ΔT gain below ~2λ; current-hogging parts want proximity | TH D6 |
| P14, S08, S53 (vendors disagree) | One topological test; one overshoot family in R_s/Z0; one ppm vs pickup trade | CT, LS |

## Recommendations for our system

1. **Make the table the rule pack's backbone.** Each record carries principle codes, the derivation, a machine-checkable regime predicate and a number status ([rule-replacements](../../ideas/physics-first/rule-replacements.md) RG1–RG3). Compute "instance" numbers from the budget at the board's regime, and flag "arbitrary" ones in explanations.
2. **Make P7 explicit in the solver API.** Return damage quantities (peak J²t, peak E, strain, Arrhenius life) beside energies, so corner, fillet and teardrop operators act only when a damage budget binds.
3. **Override these common rules:** keep the plane under inductors and never cut a body-sized hole (P13); choose reliefs by assembly process (R25); set stitching pitch from the isolation distance and f_p (S37); place snubbers by objective (P16); use guards only where h ≳ D/3 (S17); split or star only below ℓ50 (P38, P45).
4. **Use the [C] lines as regression tests,** as in [foundations-derivations](foundations-derivations.md).

## Conflicts and open questions

- **Single auditor.** The derivable vs with-regime boundary is a judgement about whether the regime binds in practice. Another auditor would move a few rows. Agreement with the 26-rule trace in [foundations-derivations](foundations-derivations.md) §R is not independent evidence (shared inputs).
- **The cut-out model** is axisymmetric, thin-sheet and air-core: no slits, off-axis parts or ferrite. One LCR measurement per inductor family, with and without cut-outs, would settle P13.
- **The reflow-relief conclusion** rests on lumped pad couplings and contradicts vendor guidance. An assembly experiment is needed.
- **Assumptions:** Kohlrausch's bound assumes cool via ends; the stitching numbers assume 0.15 mm vias and a homogenized lattice (LS: within 0–3%).

## Sources

- [C]: [da_derivations.py](../../../tools/research/physics/da_derivations.py), [da_inductor_cutout.py](../../../tools/research/physics/da_inductor_cutout.py), [da_coverage.py](../../../tools/research/physics/da_coverage.py).
- Rule numbers: the genealogy docs and [rg_proxies.py](../../../tools/research/physics/rg_proxies.py); [hv-and-manufacturing-physics](hv-and-manufacturing-physics.md) (reliefs, tombstones); [pdn-and-commutation](pdn-and-commutation.md) §7 (inductor eddies). Lenses: [VP](lens-vp.md), [CT](lens-ct.md), [SY](lens-sy.md), [LS](lens-ls.md), [TH](lens-th.md), [IN](lens-in.md), [CD](lens-cd.md).
- [S]: Foster, Bell Syst. Tech. J. 3, 1924; Holm, *Electric Contacts* (Kohlrausch's φ–θ relation, constriction resistance); Williams, J. Appl. Mech. 19, 1952; Peek, *Dielectric Phenomena in High Voltage Engineering*, 1929; Marcuvitz, *Waveguide Handbook*, 1951; Belov et al., Phys. Rev. B 67, 2003; Washburn, Phys. Rev. 17, 1921; Den Hartog, *Mechanical Vibrations*.

See also: [derivation-audit-table](derivation-audit-table.md) · [foundations](foundations.md) · [foundations-derivations](foundations-derivations.md) · [rule-basis-set](rule-basis-set.md) · [README](README.md) · [research-gaps](research-gaps.md)
