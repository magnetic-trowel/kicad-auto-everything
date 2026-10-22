# Rule genealogy: SI, differential pairs, EMC, RF, crystals, interfaces

**TL;DR**
- High-speed rules encode five quantities: **return-path inductance** (L), **propagation** (Z0, delay, loss, stubs: Z), **balance** (skew and mode conversion: Bal), **coupling** (M and Cm) and **common-mode voltage on cables and chassis** (Vcm). "Reference continuity" is the geometric cause behind most of them, not a quantity of its own.
- Many millimetre and mil rules are exact physics *in disguise* only for one stackup family. The 3W rule gives the same ~2.8% NEXT bound for **every 50 Ω microstrip** (w fixes w/h ≈ 2), but 80% for 0.25 mm traces on a 1.6 mm two-layer board [C]. Re-express such rules in units of h.
- Return-via distance enters inductance only through **ln(s/a)**; plane spacing d enters linearly. Moving a return via from 5 mm to 1.3 mm saves ~40%; halving d saves 50% [C].
- The 90° corner is negligible until f ≈ 3–4 GHz·mm / h: 14–19 GHz at h = 0.2 mm, but **1.9–2.6 GHz on a 1.5 mm two-layer board** [C]. So it is a real rule for 2.4 GHz RF on thick substrates and a myth for 4-layer digital.
- EMC rules (connector zoning, filters at the exit, no ferrite in ground) are all proxies for Vcm = jωL_ret·I between antenna parts. The MREMC closed form already replaces them; ~1 mV between cable references is the budget.

Legend as in [rule-genealogy-power-analog-thermal](rule-genealogy-power-analog-thermal.md): Origin Ph/Mf/Hb/Sp/Cg/Tl/Lg; Basis L, M, Cm, R, Z, Bal, Vcm, Res, Ins, Th, Mech, Fab ([rule-basis-set](rule-basis-set.md)); Verdict R/C/A/M/X/CT; Cost CF/2D/PEEC/FW/SP/TN/LU/GE. [C] sections refer to [rg_proxies.py](../../../tools/research/physics/rg_proxies.py), [rg_corners.py](../../../tools/research/physics/rg_corners.py) and [rg_fill_and_decaps.py](../../../tools/research/physics/rg_fill_and_decaps.py).

## Key facts

### Return paths and reference planes ([si-fundamentals](../rules/si-fundamentals.md), [stackup](../rules/stackup.md))

| ID | Rule | Orig | Physics (basis: equation; binds when) | Verdict | Replacement [cost] |
|---|---|---|---|---|---|
| S01 | Continuous reference under every fast net | Ph | **L**, **Z**, **Vcm**: return under trace, 50/80/94% within ±1/3/10h [C §N]; binds when ωL > R (above ~0.3–1 MHz [C §W]) | R | reference map + return-path detour inductance [2D/PEEC] |
| S02 | Never cross splits or slots | Ph | **L** detour, **Vcm**: Ott 1.5" slot raised plane noise 15→75 mV | R | detour nH and slot length ⊥ trace [PEEC] |
| S03 | Return via within 200 mil; 50 mil at Gen5 | Ph+Sp | **L**=(µ0d/π)ln(s/a): d 0.1 mm: 140→86 pH for s 5→1.3 mm; d 1 mm: 1.4→0.86 nH [C §C] | M: distance is logarithmic, plane spacing linear | pH budget per layer change from data rate [CF] |
| S04 | Ott's layer-change order | Ph | **L**, **Res** (cavity excitation when no via) | R | return impedance per transition [CF/FW] |
| S05 | Stitching cap ≤1 µF at split crossings | Ph | **L** of cap plus mounting ≈1 nH | R as a patch | avoid the split [PEEC] |
| S06 | ≥1.5W from voids, ≥90 mil from plane edge, ≥2h from board edge | Sp | return spread; 1.5W ≈ 3h for 50 Ω; edge **Vcm** | R if in h units; mil values are stackup proxies | edge distance k·h from a Vcm budget [2D] |
| S07 | Do not reference power planes (TI) | Ph | **L**: return through decaps adds 5–10 nH | M: R for fast edges; C when P/G gap <0.1 mm | return impedance [PEEC] |
| S08 | Review at t_r/6, terminate at t_r/2 | Ph | **Z**: reflections when round trip ≳ t_r; 100 ps → 2.6 mm, 1 ns → 26 mm [C §U] | R (constants CT) | IBIS simulation [SP] |
| S09 | Terminate beyond λ/4; series R above 1 V/ns; Z ≥ Z0/4 | Hb | **Z**: wrong variable | X | t_r-based [SP] |
| S10 | Slow edges first; series R by default | Ph | spectrum knee 0.5/t_r; **Vcm** | R | slew vs timing budget [SP] |
| S11 | Minimise every high-speed length | Sp | **Z**, **Vcm**: delay/loss yes; emissions follow Vcm, not length | M | loss dB + Vcm [CF] |
| S12 | Stubs < min(15 mil, 0.3/Gbps) | Ph | **Res**: f=c/(4l√εe); 1.27 mm → 28 GHz [C §R] | R; C at low rates | S-parameters [FW/CF] |
| S13 | Via-count limits (≤2; 0 on some SoCs) | Sp | **Z**, **Res**, **L**: via = Z step + stub + return transition | M: count is a proxy; a backdrilled via with GND vias is cheap | per-via RL/loss budget [FW] |
| S14 | Avoid power-pin corner ICs; paired P/G pins (Hartley) | Ph | **L** of package return | R | package L from IBIS [LU] |

### Crosstalk and differential pairs ([diff-pairs](../rules/diff-pairs.md))

| ID | Rule | Orig | Physics | Verdict | Replacement [cost] |
|---|---|---|---|---|---|
| S15 | 3W spacing | Sp | **M**+**Cm**: K=1/(1+(D/h)²); 2.8% for any 50 Ω microstrip; 31% for 0.1 mm traces at h 0.2 mm; 80% for 0.25 mm traces at h 1.5 mm [C §A] | M: R for controlled-Z lines (w encodes h), A for thin uncontrolled traces | D ≥ h√(1/K−1) [CF] |
| S16 | Reduce h before adding spacing | Ph | **M**, **Cm**: K ∝ h² at fixed D | R | stackup [CF] |
| S17 | Guard traces | Hb | **M**/**Cm**; −50 dB already adequate | X except end-shorted stripline | 3-D check for a named problem [FW] |
| S18 | Ground fill near traces on multilayer boards | Hb | **Z**: Z0 −3.7% at gap h, −0.9% at 2h, −0.3% at 3h [C fill]; floating fill **Res** | X as default; harmless ≥2h and stitched | gap/h + island resonance [2D] |
| S19 | Adjacent signal layers orthogonal | Ph+Tl | broadside **Cm**/**M** ∝ overlap length; also a router convention | R | overlap length × coupling [2D] |
| S20 | Pairs are not self-returning | Ph | **L**/**Z** per leg | R | per-leg reference check [2D] |
| S21 | Skew ≤ min(spec, 0.1·t_r); compensate near the mismatch | Ph | **Bal**: V_cm/V_d ≈ Δt/(2t_r); 20 ps at 100 ps = 10% [C §V] | R | mode conversion Scd21 [2D/FW] |
| S22 | Tighter coupling always lowers EMI; round corners remove skew | Hb | **Bal** limited by driver imbalance (~1:100); corners add 1.57–2p each | X | Bal budget [CF] |
| S23 | Uncoupled ≤45 mil; bends ≥135°; equal via counts | Ph | **Bal**, **Z** steps | R | mode conversion [FW] |
| S24 | Pair keep-outs 30 mil, 50 mil to clocks | Sp | **M**/**Cm** vs victim budget; absolute mils ignore h | M | K budget in h [CF] |
| S25 | Serpentine spread S1<2S; switchback ≤1"/ns of t_r | Ph | self-coupling advances the edge (**M**, **Cm**) | R | delay + FEXT [2D/SP] |
| S26 | Route 10–35° off the glass weave | Ph | local εr → intra-pair skew (**Bal**) | R ≥ ~5 Gb/s on coarse glass | weave skew model [CF] |
| S27 | Loss budgets instead of lengths (PCIe, USB3) | Ph | **Z** attenuation dB | R (already physics) | [CF/2D] |
| S28 | AC caps ≤0402, plane voided under pads | Ph | **Z**: pad excess C | R at ≥5 Gb/s | [FW] |
| S29 | Vendor skew tables differing 5–25× | Hb+Lg | **Bal**/timing with different hidden margins | M | derive from UI and receiver spec [CF] |
| S30 | DDR: match to <20% of each limit in layout | Sp | **Z**: timing margin reserve | C | IBIS across PVT [SP] |

### EMC ([emc-placement](../rules/emc-placement.md))

| ID | Rule | Orig | Physics | Verdict | Replacement [cost] |
|---|---|---|---|---|---|
| S31 | Cabled connectors on one edge | Ph | **Vcm**=jωL_ret·I_dm across plane partial inductance between connectors | R | MREMC Vcm [CF/PEEC] |
| S32 | No high-speed circuitry between connectors | Ph | **Vcm**: same | R | same [CF] |
| S33 | I/O device within 2 cm; others ≥2 cm away | Sp | **M**/**Cm** onto I/O nets → **Vcm** | M | Vcm per I/O net [PEEC] |
| S34 | Group by type, high speed far from connector | Hb | **Vcm**: longer cross-board links raise Vcm | X ("worst guideline") | Vcm [CF] |
| S35 | TVS at connector; no via or stub before it | Ph | **L**·di/dt: 8 kV contact ≈3.75×10¹⁰ A/s; 1 nH via = 37.5 V [C §E] | R | pH budget connector→TVS→ground [PEEC] |
| S36 | CMC/filter within 5 mm of entry | Ph | **Cm**/**M** coupling around the filter defeats it | R as proxy | bypass capacitance across filter (fF) [2D/PEEC] |
| S37 | Stitch every λ/20; perimeter ring vs distributed | Sp+CT | **Res**: unstitched size vs λ/2 at f_max; λ/20 = 7.2 mm at 1 GHz [C §Q] | M: usually C | largest unstitched region vs λ [CF/FW] |
| S38 | 20-H | CT | edge fringing ~h; **Res** | X generally; small benefit with planes sandwiched | full-wave if it matters [FW] |
| S39 | One solid ground; no I/O island with single-point tie; no ferrite in ground | Ph | **L** in the return path raises **Vcm** | R | Vcm [PEEC] |
| S40 | Chassis bond: many caps at HF, one LF path | Ph | **L**, **R**, **Vcm**: R vs ωL crossover | R | frequency-split impedance [PEEC] |
| S41 | 4 layers radiate ~15 dB less than 2 (Ott) | Ph | **Vcm**: DM loop area ∝ h: 1.5 vs 0.2 mm = 17.5 dB [C §S] | R | stackup in Vcm/DM model [CF] |
| S42 | Spread-spectrum clocking | Lg+Ph | **Vcm**: 120 kHz receiver bandwidth sees lower peaks; energy unchanged | R (measurement artifact) | [LU] |
| S43 | Optional footprints for filters, TVS, shields | Ph+Cg | **Vcm** uncertainty hedge | R | keep [GE] |

### RF and crystals ([rf](../rules/rf.md), [crystals-clocks](../rules/crystals-clocks.md))

| ID | Rule | Orig | Physics | Verdict | Replacement [cost] |
|---|---|---|---|---|---|
| S44 | Field-solved 50 Ω; only ground under RF on every layer | Ph | **Z**, **Cm** | R | [2D] |
| S45 | Match at the pin; shunt grounded via the named VSS pin | Ph | **L** of the ground return is part of the filter | R | [FW/SP] |
| S46 | Arcs or 135° on RF lines | Ph | **Z**: unmitred bend reaches −20 dB at ~3/h GHz·mm (C only) to ~4/h (with bend L) [C corners] | M: R at 2.4 GHz on h ≈ 1.5 mm (−20 dB per bend), marginal at 0.8 mm; X below ~10 GHz on h ≤ 0.2 mm | corner Γ from w/h [CF] |
| S47 | "50–60% optimal miter" (marked NOT FOUND in corpus) | Ph | **Z**: Douville & James 1978: M = 52+65·e^(−1.35W/h) % [S] | R, source found | [CF] |
| S48 | Via fence ≤λ_g/20 | Sp | **Res** of gaps and fence cavity | C usually | gap vs λ/2 at harmonics [FW] |
| S49 | Antenna keep-out polygon | Ph+Lg | **Cm**, **M** (near field): near-field detuning; certification | R | per-part polygon [LU] |
| S50 | RF ↔ SMPS ≥20 mm | Sp [V] | **M**/**Cm** at harmonics | M | coupling dB budget [PEEC/FW] |
| S51 | Crystal ≤12 mm, same side; ≥2–2.7 mm from chip (Espressif) | Sp | **Cm**: 0.07–0.10 pF/mm, pulling 11–20 ppm/pF [C §J]; **M** pickup | M | ppm + pickup budget [2D] |
| S52 | Guard ring; no traces under crystal; no test points | Ph | **Cm**/**M** into high-Z oscillator nodes | R | coupling fF [2D] |
| S53 | Metal can grounding; copper under crystal | CT | **Cm** | vendor | [LU] |
| S54 | I2C pull-up window from t_r and C_b | Ph | **Cm** of bus | R (already physics) | [CF] |
| S55 | Ethernet PHY↔magnetics ≥25 mm vs <1 in | CT | **Vcm** coupling vs loss | M | [CF] |

## Recommendations for our system
- Give every fast net a t_r and every layer an h before any SI rule fires; all rules above then evaluate as dimensionless groups (l/(v·t_r), D/h, s/h, f·h). See the regime table in [rule-basis-set](rule-basis-set.md).
- Replace S03/S05/S07 with one return-transition budget in pH (RG11). Replace S15/S24 with a K budget in h (RG5). Replace S46/S47 with a corner Γ check scoped by f_max·h (RG12).
- Use MREMC Vcm as the single EMC placement objective (S31–S36, S39); rank findings by mV, not by rule count ([checkers-si-emi](../rules/checkers-si-emi.md) F).
- Keep CT rules (S37, S38, S53, S55) as selectors; resolve them with a solver, not a vote.

## Conflicts and open questions
- **S03 vs S07:** both are return-inductance rules; on a tight P/G pair (<0.1 mm) a power-plane reference costs little above a few hundred MHz. The selector is the P/G spacing and edge rate.
- **S11 vs S25/S30:** "short" fights length matching; the budget is timing or skew, not length.
- **S46:** Gupta and Kirschning capacitance agree within 3%; their bend-inductance formulas differ ~4×, so the "with L" column is soft. A 2-D/3-D check should calibrate.
- The closed-form CPWG formula overstates fill effects at s ≫ h (it predicted −6.5% at 5h; the 2-D solve gives −0.1%), so the fill result uses the solve.

## Sources
- research notes: [rules_highspeed_emi.md § 1–10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md); [interface_rule_packs.md § 1–9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md); [verification_rules.md § 1A, 2, 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- Johnson, corners and pairs: https://www.sigcon.com/Pubs/edn/bigbadbend.htm, https://www.sigcon.com/Pubs/edn/CMAofSkew.htm [P]
- LearnEMC guideline pages: https://learnemc.com/not-so-good-emc-design-guidelines [P]
- Microstrip corner closed forms (Kirschning): https://qucs.sourceforge.net/tech/node76.html [S]; Gupta, Garg, Bahl, *Microstrip Lines and Slotlines* (bend C and L) [S]
- Douville & James, IEEE T-MTT 26(3):175–182, 1978, via https://techdocs.altium.com/display/ADOH1/Chamfered+Routing [S]

See also: [rule-basis-set](rule-basis-set.md), [rule-genealogy-power-analog-thermal](rule-genealogy-power-analog-thermal.md), [rule-genealogy-routing-style-dfm](rule-genealogy-routing-style-dfm.md), [../rules/myths-and-contested.md](../rules/myths-and-contested.md)
