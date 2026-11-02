# Derivation audit: which rules of thumb follow from first principles

Scope: method, verdict counts and nine short derivations for the 160 genealogy rules. Not here: one row per rule -> [derivation-audit-table](derivation-audit-table.md); the 12 quantities behind the rules -> [rule-basis-set](rule-basis-set.md); principles F1–F7 -> [foundations](foundations.md).
Keys: derivation audit, derivable, derivable-with-regime, habit-wrong, convention, legal, not derivable, principle D, P7, damage, number status, instance number, Foster, three values per pin, guard traces, 90° corners, switch node, Kelvin, snubber, thermal reliefs, λ/20 stitching, inductor cut-out, Kohlrausch

[C] = [da_derivations.py](../../../tools/research/physics/da_derivations.py) (§A–§H), [da_inductor_cutout.py](../../../tools/research/physics/da_inductor_cutout.py), [da_coverage.py](../../../tools/research/physics/da_coverage.py) (parses the table). Other numbers: genealogy docs and lenses, cited inline.

## Method

160 rules = [P01–P59](rule-genealogy-power-analog-thermal.md), [S01–S55](rule-genealogy-si-emi-rf.md), [R01–R46](rule-genealogy-routing-style-dfm.md); one attempted derivation each, one line in the [table](derivation-audit-table.md). **Derived** = the line yields the rule's direction (and number, if any) from principles, geometry and material constants, and states the regime where it holds.

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

Verdicts: **derivable** (holds wherever the rule's object exists), **derivable-with-regime** (inside a stated regime only), **convention** (physically neutral choice), **legal** (a standard sets the number), **habit-wrong** (derivation contradicts the rule), **not derivable** (principles cannot produce it). Numbers: derived, instance, data, arbitrary.

## Coverage [C da_coverage]

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

Numbers: of 67 stated numbers, 12 derive, 23 are a budget evaluated at one regime (instance), 14 data, 18 arbitrary [C]. Store budgets; compute numbers.

1. Physics corpus sound but regime-bound: 90 of 91 physics rules derive, 49 only with a regime; 102 rules need only P1–P6.
2. Locality and scales (θ, Z/Z0, ℓ_m, decay lengths) appears in 46% of derivations: it turns a slogan into a rule.
3. Simplicity proxies are one regime's budgets: all but one derive, none cleanly ("3W", "2 mm", "200 mil", "λ/20").
4. Habits fail by variable: 11 of 15 use the wrong one (pins, clock λ, signal width, area). Three hold narrowly: IPC-2221 (thermal only), guards (thick boards), hatching (flex).

## Nine short derivations

**D1. Three values per pin (habit-wrong; P2, P5).** Foster: lossless one-port dX/dω = 4(W_m + W_e)/‖I‖² > 0, so poles and zeros of X alternate: two capacitors with different series resonances force an anti-resonance between them, limited only by loss. 10 µF + 100 nF + 1 nF at 1 nH each: 11 Ω peak near 130 MHz with 10 mΩ ESR; three 10 µF parts: no peak [C da §D]. Holds only where lead inductance scales with value (leaded parts).

**D2. Guard traces (habit, regime-bound; P3).** Over a plane each trace and its image form a line dipole: field at mid-gap already down ~(h/D)². A grounded guard removes only the remnant: −1–3% at h = 0.1 mm, −48% at h = 1.6 mm (D = 5 mm; [lens-sy](lens-sy.md) D1). Guards are a two-layer tool (h ≳ D/3).

**D3. No 90° corners (myth; needs P7, not P2).** A bend has two corners with dual physics: inside (concave) crowds current, J ∝ r^(−1/3); outside (convex) crowds field in an HV gap, E ∝ r^(−1/3) [C da §H]. Loss moves only 0.06 squares; SI sees the excess C only above f·h ≈ 3 GHz·mm. Corners matter where the governing quantity is local: pulses shorter than w²/α (0.8 ms at w = 0.3 mm), fusing, HV, ESD.

**D4. Switch-node copper minimal (world-charge rule, not node-capacitance rule; P1, P3).** Charge conservation on a surface around the board: I_CM = −jω·Σ C_i,ext·V_i ([lens-ct](lens-ct.md) D2). Only charge whose field ends outside the cell drives common mode; capacitance to the node's own return plane is free. Over a plane the node is a vertical dipole ∝ ∫V dA, coupling ∝ h^0.19 (SY). Variable = outward area at voltage; thinner prepreg does not help, unlike for loops.

**D5. Kelvin taps (reciprocity rule; P3).** A sense port reads source current density J through its lead field E_L: V = (1/I_L)∫J·E_L dV ([lens-sy](lens-sy.md) P1). Error vanishes when taps sit on the load's equipotentials and the sense cycle shares no piece with the load ([lens-cd](lens-cd.md) D4). At AC a voltage belongs to a loop: route the pair together, filter at the IC. The resistive picture is the DC case.

**D6. Snubber at the switch pins (placement by objective; P5).** First-peak overshoot: L_s → 0. Ring decay, emission, loss: tuned absorber (Den Hartog); branch impedance R_s + jZ0(l − 1/n) is resistive when L_s·C_s = L·C_oss. C_s = C_oss, L_s ≈ L: Q ≈ 1 at 72 mW vs 216 mW for C_s = 3·C_oss ([lens-th](lens-th.md) D3).

**D7. Thermal reliefs (manufacturing; P5, P4, MP).** WF makes a spoke's thermal and electrical resistance one number, R_el = ρk·R_th: 37 K/W costs 0.25 mΩ [C da §A].
- Hand or wave soldering: relief cuts the joint's drain 1.8–4.2× (its purpose).
- Reflow: pad couples ~0.1 mW/K to the oven, 27–54 mW/K to the plane, so it follows the plane either way; isolating it would take ≥ 10⁴ K/W (≥ 66 mΩ).

**D8. Stitch every λ/20 (proxy; P4, P2, P5).** 2-D via lattice = wire medium: k_p² = 2π/(a²(ln(a/2πr) + 0.53)) (pitch a, via radius r), independent of plane spacing.
- Below cut-off the cavity field decays 11–19 dB per pitch at any frequency: pitch follows the isolation distance. Frequency enters only through f_p > f_max (a ≲ λ/4); λ/20 at 2.45 GHz gives f_p = 6.2·f_max [C da §B].
- Single fence row = inductive grid leaking ≈ 2(a/λ)·ln(a/2πr): −19 dB at λ_g/20, −9 dB at λ_g/10.
- Vias reflect; they do not damp (TH).

**D9. Three vendor numbers** [C da §A, §G]:

| Rule | Derivation | Result |
|---|---|---|
| PDN peak ≤ 1.57·Z_t | load toggling at the resonance has fundamental (2/π)·ΔI | Z_pk ≤ (π/2)·Z_t |
| TI's ESD corner radius ≥ 2.6 mm | isolated feature at 8 kV: surface field ≈ V/r; air breaks down at 3 kV/mm | r = V/E_bd = 2.7 mm (Peek: 1.5 mm) |
| ≥ 1 via per amp | end-cooled barrel self-heats ΔT = V²/(8L0T) (Kohlrausch, from WF) | 1 A heats a 1.3 mΩ via by 0.03 K; 10 K takes ~18 A, so loop L or IR sets the count |

## What does not derive, and principle D

**Not derivable (2).** MLCC DC-bias derating (P27): ferroelectric constitutive law, an F2 break. Vendor skew tables (S29): undisclosed margins. Physics states the budget each replaces, not the number.

**Habit-wrong (12):** 11 habit rules + 20-H; wrong variable or obsolete regime (leaded capacitors, immersion etching, clock-λ termination).

**Principle D (P7): failure follows local maxima and accumulated damage, not energy.**
- Steep rates: Arrhenius ageing doubles per 10 °C; Coffin–Manson fatigue is a power law; breakdown, yield, fracture are thresholds.
- Local: rates see corner singularities r^(π/α−1); governing quantity = maximum or high-power norm, not a quadratic energy.
- Energy principles cannot stand in: Thomson bounds a corner's loss effect at ≤ 0.3 squares, says nothing about pulses, HV, ESD, fatigue.
- 12 rules need P7: P47–P49, P52, P58, R01, R03, R18, R20, R30, R35, R39. Seven derive only with it, e.g. teardrops (stress at a re-entrant corner ∝ r^(−0.46) [C da §H]), MLCC distance from a V-score, rounded pulse corners. Three are legal tables whose direction it explains.
- In [foundations](foundations.md) P7 = F6's damage clause + T11. Give it its own objective class in the solver API: return damage quantities (peak J²t, peak E, strain, Arrhenius life) beside energies, so corner, fillet and teardrop operators act only when a damage budget binds [I]. Its rate laws are constitutive data, like ε and σ.

Scope notes:
- Reciprocity fails in moving media: "electrolytics upstream" (P58) needs advection, an F2 break.
- Manufacturing physics is mostly P1–P6 in other fields plus process data: 22 of 24 process rules have such a core: surface energy (tombstoning, wicking: P2), elastic strain with Saint-Venant decay (V-score, warp: P2, P4), screened transport in a plated hole (aspect ratio: P4), z-score margins (annular ring, DRC margin: P6).
- Cost is an input the set lacks: via-in-pad and one-sided assembly need it ([research-gaps](research-gaps.md) gap 19).
- T1 derives 18 rules: hot loops, laminated buses, gate loops, plane pairs, TIA and feedback nodes, crystal nodes, 50 Ω lines, voided pads, necks, NFPs. No coupling rule (3W, guards, switch-node area, connectors), as T1's self-term condition predicts. Rules that hold for another reason than the usual one: switch-node copper (board–world charge), Kelvin (reciprocity), snubbers (designed loss).

## Common rules and what governs them

Each rule record carries principle codes, derivation, machine-checkable regime predicate and number status ([rule-replacements](../../ideas/physics-first/rule-replacements.md) RG1–RG3); compute "instance" numbers from the budget at the board's regime, flag "arbitrary" ones in explanations. Override the rules below as stated.

Numbers for each line: the rule's row in the [table](derivation-audit-table.md).

| Rule | Override (verdict, regime, reason) | Basis |
|---|---|---|
| P05 loop-area tiers | Self L follows h × squares (P2); area × h = image quadrupole moment sets far coupling and DM emission (P3). Use tiers for emission at fixed h, not overshoot | VP, CT D5, SY, IN |
| P11, P38, P45, S39 star and split grounds | Pay only where ℓ50 = R_s/(2πμ0f) exceeds the aggressor–victim distance, far below the audio rule's 100 kHz. A single tie is exact only as an articulation point; place it at the aggressor's stagnation point (leak ∝ w⁴, not w²) | VP D5, LS, CT D3, CD D3 |
| S17 guard traces | Only where h ≳ D/3, cutting coupling up to ~6 dB | SY D1 |
| S16 reduce h before spacing | Loops and narrow traces only, not wide dv/dt copper | SY D1 |
| S15 3W | Accidental D/h rule (w/h ≈ 2 at 50 Ω); over-spaces stripline | IN D3, LS |
| "As close as possible" (P02, P24, S35, S51) | Linear for series paths and node C; logarithmic for plane spreading, bounded by a screening length that diverges at f_p [C da §F] | LS, VP D3 |
| P16 snubber at the pins | By objective: overshoot → closest; ring Q and loss → tuned L_s·C_s ≈ L·C_oss | TH D3 |
| P13 copper under inductors (Rohm and TI disagree) | Keep the plane; never a body-sized cut-out; large cut-outs (≥ 2–3× winding radius) cut loss and ΔL (0.5–2 MHz) but unshield lower layers [C da_inductor_cutout] | CT holes, LS ℓ_m, SY images |
| R25 thermal reliefs | Per process: hand, wave, THT soldering yes; reflow no physical effect, balance set by what the pad is tied to (D7) | WF [C da §A]; WS7 |
| S37, S48, R24 stitching at λ/20 | 2-D lattice: pitch from isolation distance plus f_p > f_max; 1-D fence: per-row leakage from a/λ (D8). Damping needs edge resistors | LS, TH D4 [C da §B] |
| P41 driven guard (fA) | Removes leakage and effective C within the buffer's bandwidth; dielectric noise 4kT·ωC·tanδ survives | TH |
| P57 spread hot parts | No mean-ΔT gain below ~2λ; current-hogging parts want proximity | TH D6 |
| P14, S08, S53 (vendors disagree) | One topological test; one overshoot family in R_s/Z0; one ppm vs pickup trade | CT, LS |

## Open questions

- **Single auditor.** derivable vs with-regime is a judgement about whether the regime binds in practice; another auditor would move a few rows. Agreement with the 26-rule [trace](foundations-derivations.md#r-rule-of-thumb-trace) is not independent (shared inputs).
- **Cut-out model** is axisymmetric, thin-sheet, air-core: no slits, off-axis parts, ferrite. One LCR measurement per inductor family, with and without cut-outs, would settle P13.
- **Reflow-relief conclusion** rests on lumped pad couplings and contradicts vendor guidance; needs an assembly experiment.
- **Assumptions:** Kohlrausch's bound assumes cool via ends; stitching numbers assume 0.15 mm vias and a homogenized lattice (LS: within 0–3%).

## Sources

- [C]: [da_derivations.py](../../../tools/research/physics/da_derivations.py), [da_inductor_cutout.py](../../../tools/research/physics/da_inductor_cutout.py), [da_coverage.py](../../../tools/research/physics/da_coverage.py).
- Rule numbers: genealogy docs and [rg_proxies.py](../../../tools/research/physics/rg_proxies.py); [hv-and-manufacturing-physics](hv-and-manufacturing-physics.md) (reliefs, tombstones); [pdn-and-commutation](pdn-and-commutation.md) §7 (inductor eddies). Lenses: [VP](lens-vp.md), [CT](lens-ct.md), [SY](lens-sy.md), [LS](lens-ls.md), [TH](lens-th.md), [IN](lens-in.md), [CD](lens-cd.md).
- [S]: Foster, Bell Syst. Tech. J. 3, 1924; Holm, *Electric Contacts* (Kohlrausch's φ–θ relation, constriction resistance); Williams, J. Appl. Mech. 19, 1952; Peek, *Dielectric Phenomena in High Voltage Engineering*, 1929; Marcuvitz, *Waveguide Handbook*, 1951; Belov et al., Phys. Rev. B 67, 2003; Washburn, Phys. Rev. 17, 1921; Den Hartog, *Mechanical Vibrations*.
