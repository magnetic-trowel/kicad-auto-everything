# Rule basis set: the few physical quantities behind 160 layout rules

**TL;DR**
- The 160 rules audited in the three genealogy docs reduce to **12 physical quantities**: loop/partial inductance L, mutual and shared-path coupling M, node capacitance Cm, resistance and current density R, propagation Z (impedance, delay, loss), balance Bal, radiating common mode Vcm, distributed resonance Res, insulation Ins, thermal Th, mechanical strain Mech and process margin Fab. Two **non-physical axes** remain: review cost (Cog) and standards (Std).
- Inductance dominates: it appears in 40 rules, then Cm 29, M 27, Z 23, Th 22, Vcm 20, R 17, Res 16, Fab 13, Ins 8, Bal 5, Mech 3 (counted from the tables). "Return-path continuity" and "loop area" are **not** basis quantities; they are geometric causes that show up in L, Z, Bal, Vcm and Res.
- Most rules fail by **regime, not direction**. Physics-origin rules are about right in 80 of 91 cases; simplicity proxies are mixed in 16 of 23; habit/legacy rules are wrong in 10 of 15. Every rule record therefore needs a regime predicate, and about 14 dimensionless groups supply them.
- Proxy words are overloaded. "Short" touches seven quantities, "keep away" six, and "wide" six, two of them for the worse (node capacitance on switching nodes, spacing with heavy copper). Most rule conflicts are two rules optimising different quantities, or one quantity in different regimes.
- The physics is cheap to evaluate: 143 of 160 rules can be replaced by a closed form, lookup, 2-D solve, PEEC model, thermal network or SPICE run; only 8 strictly need full-wave or FEM. Rules stay useful as **priors for synthesis**, not as the judge.

## Key facts

### The basis set

| Code | Quantity | Unit | Governing relation (examples) | Where the budget lives | Cheapest adequate solver | Rules |
|---|---|---|---|---|---|---|
| L | Loop and partial self-inductance of a current path (incl. via, mounting, ESL) | nH, pH | V=L·di/dt; L′≈µ0h/w (w≫h); via 0.2h(ln(4h/d)+1) nH; cavity (µ0d/π)ln(s/a) | overshoot, ground bounce, PDN HF floor, ESD clamp, efficiency | CF → PEEC | 40 |
| M | Mutual inductance and shared-branch impedance between loops | nH, mΩ | V=M·di/dt; V=Z_shared·I | crosstalk, FB noise, ground noise in LSB | PEEC | 27 |
| Cm | Capacitance of high-dv/dt or high-Z nodes to victims, to the world, or as load | pF, fF | i=C·dv/dt; C′=√εe/(c·Z0) | injected current, crystal ppm, op-amp peaking, bus t_r | 2D → 3-D electrostatic | 29 |
| R | Resistance and current density (DC, skin, crowding) | mΩ, A/mm² | R=ρl/(wt); δ=√(ρ/πfµ0); corner 0.56 □ | IR drop, I²R, Kelvin error, fusing | CF → 2D sheet solve | 17 |
| Z | Guided-wave propagation: Z0 profile, delay, loss, stubs | Ω, ps, dB | Γ=(Z2−Z1)/(Z2+Z1); f_stub=c/(4l√εe) | eye, timing, return loss, loss budget | 2D + CF → FW | 23 |
| Bal | Balance and mode conversion of pairs and filters | dB (Scd21), ps | V_cm/V_d≈Δt/(2t_r) | mode conversion, skew | 2D → FW | 5 |
| Vcm | Radiating source strength: common-mode voltage on cables, chassis, heatsinks (and DM loop moment) | mV, µA, dBµV/m | V_cm=jωL_ret·I; E_DM∝f²·A·I | emissions and, by reciprocity, immunity | CF (MREMC) → FW | 20 |
| Res | Resonance of distributed structures: plane cavity, PDN anti-resonance, stubs, islands, slots | MHz, Q | f_mn=(c/2√εr)√((m/a)²+(n/b)²); Q | PDN peaks, cavity emission, stub notches | CF → FW | 16 |
| Ins | Insulation: field, surface path, leakage, migration | kV/mm, mm, pA | I=V/(ρ_s·N□); Paschen min ≈327 V | safety spacing, leakage error | LU + GE | 8 |
| Th | Thermal resistance and temperature, incl. gradients | °C/W, °C, °C/mm | fin length √(kt/2h); R=L/(kA) | T_J, lifetime, drift, thermal EMF | TN → FEM | 22 |
| Mech | Strain and stress | µε, N | beam bending, CTE mismatch | MLCC cracks, joint fatigue, flex | CF → FEM | 3 |
| Fab | Process margin and defect probability | µm, ppm | margin/σ of etch, drill, registration, wetting | yield, voids, tombstones | LU + GE | 13 |
| Cog / Std | Review and editability; legal tables | — | not physics | acceptance; certification | GE, LU | 5 / 7 |

Counts are rules that name the quantity in the "Physics" column of [power-analog-thermal](rule-genealogy-power-analog-thermal.md) (P01–P59), [si-emi-rf](rule-genealogy-si-emi-rf.md) (S01–S55) and [routing-style-dfm](rule-genealogy-routing-style-dfm.md) (R01–R46); 56 rules name two or more.

### Rule-to-quantity index (the sparse matrix)

| Code | Rules naming it |
|---|---|
| L | P01–06, P16, P19, P21, P23–26, P35, P38, S01–05, S07, S13, S14, S20, S35, S39, S40, S45, R05, R06, R09, R10, R15–17, R22, R26, R27, R32, R34 |
| M | P09–11, P13, P14, P17, P30, P39, P40, S15–17, S19, S24, S25, S33, S36, S49–52, R05, R11–13, R16, R46 |
| Cm | P07–10, P12, P18, P42, P51, S15–17, S19, S24, S25, S33, S36, S44, S49–54, R05, R11, R12, R15, R29, R46 |
| R | P10, P15, P31, P32, P36, P37, P45, P46, S40, R01, R05, R08, R20, R26, R32, R34, R35 |
| Z | S01, S08, S09, S11, S13, S18, S20, S23, S27, S28, S30, S44, S46, S47, R01, R05, R07, R08, R13, R15, R23, R28, R30 |
| Bal | S21–23, S26, S29 |
| Vcm | P18, P35, P38, S01, S02, S06, S10, S11, S31–34, S39–43, S55, R14, R45 |
| Res | P21, P22, P28, P29, S04, S12, S13, S18, S37, S38, S48, R06, R23, R24, R28, R29 |
| Ins | P41, P47–52, R46 |
| Th | P08, P15, P31, P32, P34, P37, P43, P44, P46, P53–58, R08, R20, R25, R26, R34, R38, R46 |
| Mech | R18, R31, R39 |
| Fab | P49, P59, R04, R06, R17–19, R21, R33, R36, R37, R41, R42 |
| Cog | R02, R03, R40, R43, R44 |

P20 (bootstrap ratio) and P27 (MLCC derating) are schematic and part-choice rules with no layout quantity; P33 encodes nothing.

### Why these twelve and not others
- **Independence.** For each quantity there are rules that bind on it alone: L (P01 hot loop), M (P11 single tie), Cm (P42 summing node), R (P36 Kelvin), Z (S12 stubs), Bal (S21 skew), Vcm (S31 connector edge), Res (P22 three values), Ins (P47 creepage), Th (P54 copper area), Mech (R39 MLCC near V-score), Fab (R19 annular ring). Two layouts can match in all others and differ in that one.
- **Merged, not separate:** "crosstalk" = M + Cm (+ Z for saturation); "ground bounce" = L or M of a shared branch; "PDN impedance" = L + R + Res + capacitor data; "EMI" = Vcm (+ Res); "SI" = Z + Bal; "loop area" = L at fixed h, and Vcm only for DM emission (Hubing: radiation is not proportional to loop area for well-referenced lines).
- **Rejected as quantities:** "reference continuity" (it is the cause of excess L, Z steps, mode conversion and Vcm, and is measured through them); "distance" (meaningful only through M, Cm, Th, Ins); "via count" (L, Z, Res, Fab); "neatness" (Cog).
- **Finer structure** ([foundations](foundations.md), [derivation-audit](derivation-audit.md)): M has two parts, shared-edge coupling (removable by re-routing) and field coupling (never zero). Bal is a view of Vcm: mode conversion happens only where current division changes, V_cm = Δχ·V_dm ([lens-sy](lens-sy.md)); budgets may still be written in dB and ps. Three further quantities complete the basis: Q destination (where dissipation and damping go), life fraction (damage from extremes and accumulation) and τ_e (insulator charge relaxation).
- **One step further down:** all electrical quantities except Ins are views of four solver primitives: the resistance matrix R, the partial-inductance matrix Lp, the capacitance (or potential-coefficient) matrix, and retardation τ. That is exactly a PEEC model; full-wave is PEEC with retardation kept. Thermal is a conductance network. So a physics-first checker needs about four engines, not 160 rules ([solver-ladder](solver-ladder.md)).

### Proxy words decoded
● = the word mainly targets this quantity; ○ = secondary effect; ▲ = the word makes this quantity *worse* (a hidden trade-off).

| Proxy word | L | M | Cm | R | Z | Bal | Vcm | Res | Ins | Th | Mech | Fab |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| short | ● | ○ | ○ | ● | ● | | ○ | ○ | | | | |
| wide | ○ (● if plane close) | | ▲ | ● | ● | | | | | ● | | ▲ (heavy Cu space) |
| close to the plane (small h) | ● | ● | ▲ (node load) | | ● | | ● | | | ○ | | |
| close part-to-part | ● | ▲ | ○ | ○ | | | | | | ▲ | | ▲ |
| direct / no detour | ● | | | ○ | ○ | | ○ | | | | | |
| no vias | ● | | ○ | | ● | ○ | | ● (stubs) | | ▲ | | ○ |
| keep away | | ● | ● | | | | ○ | | ● | ● | ○ | |
| solid plane, no split | ● | ○ | | | ● | ○ | ● | ○ | | ○ | | |
| small loop | ● | ● | | | | | ○ | | | | | |
| one ground, single tie | ○ | ● | | ● | | | ○ | | | | | |
| symmetric / matched | | | | ○ | ○ | ● | ○ | | | ○ | | |
| stitch | ○ | | | | | | ○ | ● | | | | |
| pour / fill | ● (2-layer) | | ▲ (switching nodes) | ● | ▲ (gap <2h) | | | ▲ (floating) | | ● | ○ | ○ |
| 45° / curves | | | | ○ | ○ (RF only) | | | | ○ (HV, ESD) | | ○ (flex) | ○ |
| thermal relief | ▲ | | | ▲ | | | | | | ▲ | | ● |

### Regime selectors: when does a rule bind?

| Dimensionless group | Binds when | Gates rules |
|---|---|---|
| Electrical length l·√εe/(c·t_r) | >1/6 review, >1/2 terminate | S08, S12, S13, R07 |
| Return spread vs distance: ℓ50(f) = R_s/(2πμ0f) against the aggressor–victim distance D ([derivation-audit](derivation-audit.md)) | ℓ50 < D: plane rules; ℓ50 > D: star/Kelvin rules (only below ~6 kHz at 10 mm on 1 oz) | P11, P38, P45, S01, S39, S40 |
| Coupling D/h | K=1/(1+(D/h)²) above victim budget | S15, S16, S24, R12, R46 |
| Plane proximity w/h | w≫h: L∝h/w; w≲h: L only log in w | P04, P24, R09, R34 |
| Size over half-wavelength a·2√εr·f/c | >~0.3 at f_max | P22, S37, S48, R28 |
| Inductive noise L·(di/dt)/V_margin | >~0.1 | P01–P06, P19, S35 |
| Capacitive injection C·(dv/dt)·Z_victim/V_allow | >~1 | P07, P10, P42, S52 |
| IR ratio I·R/(ε·V_rail) | >1 | P31, P32, P36 |
| Thermal P·R_th/ΔT_allow | >1 | P53–P58 |
| Fin ratio r_copper/√(kt/2h) | >1: added area weak | P54, R34 |
| Skew Δt/(2t_r) vs CM budget | above budget | S21, S26, S29 |
| Voltage V_peak/327 V; pollution degree | <1: no gas breakdown; tracking still applies | P47–P50 |
| Leakage V/(ρ_s·N□)/I_allow | >1: guard needed | P41 |
| Corner f_max·h/(3 GHz·mm) | >~1 | R01, S46 |

### Rule conflicts explained by physics

| Conflict | Rules | Type | Resolution |
|---|---|---|---|
| Switch-node area: small vs large for heat and current | P07 vs P08, R34 | different quantities (Cm vs Th, R) | cool through the quiet node; SW area sized by current density only |
| Guard copper vs no copper at the input | P41 vs P42 | different (Ins vs Cm) | pick by signal current and bandwidth |
| Star vs plane grounding | P45, S40 vs S39, P11 | same (return Z), regime ℓ50(f) vs D | star/Kelvin only while the return spreads past the victim (DC to a few kHz at board scale), plane above |
| "Smallest cap closest" vs "lowest L closest" | P23 | same (L), legacy regime (leaded parts) | rank by mounting L |
| Decap "within 2 mm" vs "location doesn't matter" | P24 | same (L), regime: plane spacing d | spreading term (µ0d/π)ln(s/a) |
| Return via 200 mil vs 50 mil | S03 | same (L), ln(s) vs linear d | pH budget; reduce d first |
| Copper under inductor: keep vs remove | P13 | same (M), sign set by leakage flux and f | per-part field solve |
| CIN/COUT grounds apart vs together | P14 | same (M) | Z_shared at ring frequency |
| Short vs over-plane vs length-matched | R05, R10, R13, S11 | different (L vs Z delay vs Vcm) | budgets per quantity |
| Thermal relief vs direct connect | R25 vs R26 | different (Fab vs Th, L, R) | assembly process + loop budget |
| Perimeter vs distributed stitching | S37 | same (Res), different modes | largest unstitched dimension vs λ/2 |
| Fill on 2-layer vs multilayer | R27 vs R28 | same (L, Z), regime: layer count | stitched return on 2-layer; s≥2h fill on multilayer |
| Crystal near (≤12 mm) vs not too near (≥2 mm) | S51 | different (Cm, M vs heat and coupling from the chip) | ppm + pickup budgets |
| Heavy copper vs fine pitch | P34 vs R36 | different (Th, R vs Fab) | per-layer copper choice |
| Slow edges vs efficiency | S10 vs P01 | different (Vcm vs switching loss) | explicit EMI vs efficiency trade |
| Microstrip vs stripline for fast pairs | stackup CT | different (Res of stubs vs Vcm, loss) | stub strategy decides |

### Origin versus verdict (primary origin of each rule)

| Primary origin | Rules | About right | Mixed by regime | Conservative | Wrong | Anti-conservative / contested |
|---|---|---|---|---|---|---|
| Physics | 91 | 80 | 7 | 1 | 0 | 3 |
| Simplicity proxy | 23 | 3 | 16 | 4 | 0 | 0 |
| Manufacturing | 16 | 11 | 1 | 3 | 0 | 1 |
| Habit / legacy | 15 | 0 | 4 | 0 | 10 | 1 |
| Cognition / tool / legal / contested | 15 | 8 | 2 | 2 | 1 | 2 |

### The working hypothesis, sharpened
- **Adopted:** rules are lossy encodings of these quantities, and decompressing them works. The loss is mostly **regime** (stackup h, t_r, frequency, power, process), so a rule record without its regime predicate is the defect.
- **Sharpened:** "make the realisation invisible" is wrong for structures where the parasitic *is* the circuit: RF matching, snubber loops, Kelvin taps, spark gaps, heat spreaders, filters, antennas. There the goal is "designed and budgeted".
- **Kept non-physical:** Std (creepage tables), Fab and Cog are real constraints with their own budgets; physics may tighten Std, never relax it.
- **Attacked:** physics is simpler to *evaluate* than the rule corpus, but not to *synthesise*. Rules remain good warm starts and move generators for search; the basis quantities judge.

## Recommendations for our system
- Make the 12 codes the type system for budgets in the constraint IR ([constraint-ir](../architecture/constraint-ir.md), I1/I2 in [intent-and-why](../../ideas/original/intent-and-why.md)); every rule pack entry names its quantity, regime group and budget.
- Build four engines first: closed-form library, 2-D cross-section/sheet solver, PEEC-lite (R, Lp, C), thermal network. They cover about 89% of the rules; add full-wave only for Res and Vcm sign-off.
- Treat the proxy matrix as a lint: an LLM-authored constraint using a proxy word must resolve it to a column (RG10 in [rule-replacements](../../ideas/physics-first/rule-replacements.md)).
- Resolve conflicts by computing both rules' quantities on the actual geometry; same-quantity conflicts become regime lookups, different-quantity conflicts become explicit Pareto choices for the user.

## Conflicts and open questions
- The counts come from our own classification of 160 rules; another auditor would shift some rows between "about right" and "mixed". The ranking (L ≫ others) is robust.
- Ins mixes field (physics) and table (Std). Splitting physics-insulation (leakage, migration, Paschen) from legal spacing may be cleaner.
- Mech and Fab are thinly covered by the corpus; [thermal-hv-mfg](../../ideas/physics-first/thermal-hv-mfg.md) should extend them.

## Sources
- The three genealogy docs (all row-level sources are cited there) and their scripts: [rg_proxies.py](../../../tools/research/physics/rg_proxies.py), [rg_corners.py](../../../tools/research/physics/rg_corners.py), [rg_fill_and_decaps.py](../../../tools/research/physics/rg_fill_and_decaps.py)
- research notes: [verification_rules.md § 1–3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md); [rules_highspeed_emi.md § 9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)
- LearnEMC, "the most important EMC design guidelines" (radiation vs loop area): https://learnemc.com/the-most-important-emc-design-guidelines [P]
- Ruehli's PEEC formulation (R, Lp, P, τ) as the common substrate: A. E. Ruehli, "Equivalent circuit models for three-dimensional multiconductor systems", IEEE T-MTT 22(3), 1974 [S]

See also: [vocabulary](vocabulary.md), [critics ideas](../../ideas/physics-first/critics.md), [solver-ladder](solver-ladder.md), [../rules/myths-and-contested.md](../rules/myths-and-contested.md), [../rules/rule-pack-format.md](../rules/rule-pack-format.md)
