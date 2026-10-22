# Rule genealogy: power, PDN, analog, isolation, thermal

**TL;DR**
- Almost every power rule is a proxy for one number: **loop inductance in nH** (hot loop, CIN distance, "no vias", area tiers, decap distance, gate drive, ESD). The proxies disagree across stackups because inductance scales with height-to-return h far more than with length or width.
- Three famous power rules are **anti-conservative** in a common regime: IPC-2221 width on ≤3.3 V rails (IR drop), "decap within N mm" on 2-layer or thick-dielectric boards, and "15.3 cm²/W" for a single hot part on 1 oz copper (area beyond the ~25 mm fin length barely helps).
- Analog rules split by **which parasitic dominates**: shared-path impedance (grounds, Kelvin), node capacitance (summing nodes, fast TIAs) or leakage (electrometers). The same copper (a guard or a pour) helps one regime and hurts another.
- Creepage and clearance tables are mostly **standards-legal** plus contamination and surge physics, not steady-state field physics: mean fields at mains clearances are ≤1.6 kV/mm, and below the ~327 V Paschen minimum air does not break down at any gap. Keep the tables; add physics side checks.
- Each rule below gets a replacement budget. All but two need only a closed form, a lookup, a 2-D solve, a PEEC/thermal network or SPICE; P13 needs a magnetostatic FEM and P52 a 3-D field solve.

Legend. **Origin:** Ph physics, Mf manufacturing, Hb habit/legacy, Sp simplicity proxy, Cg cognition, Tl tool limit, Lg standard/legal. **Basis** (defined in [rule-basis-set](rule-basis-set.md)): L loop/partial inductance, M mutual/shared-path coupling, Cm node capacitance, R resistance and current density, Z propagation, Bal balance, Vcm common mode on antennas, Res resonance, Ins insulation, Th thermal, Mech strain, Fab process margin; non-physical axes Cog (review and editability) and Std (standards). **Verdict:** R about right, C conservative, A anti-conservative, M mixed (C in one regime, A in another), X wrong as stated, CT contested. **Cost:** CF closed form, 2D field solve, PEEC quasi-static 3-D, FW full-wave, SP circuit/SPICE, TN thermal network/FEM, LU lookup, GE geometry only. [C] numbers come from [rg_proxies.py](../../../tools/research/physics/rg_proxies.py) (sections A–W), [rg_corners.py](../../../tools/research/physics/rg_corners.py) and [rg_fill_and_decaps.py](../../../tools/research/physics/rg_fill_and_decaps.py), FR-4 εr 4.3.

## Key facts

### Switching converters ([hot-loops](../rules/power/hot-loops.md), [buck](../rules/power/buck.md), [flyback](../rules/power/flyback-offline.md))

| ID | Rule | Orig | Physics (basis: equation; binds when) | Verdict | Replacement [cost] |
|---|---|---|---|---|---|
| P01 | Hot loop smallest; place it first | Ph | **L**: V=L·di/dt; binds when L·di/dt > ~10% of V_DS margin (≥0.5 A/ns) | R | nH budget from overshoot and efficiency (EPC: 0.4→2.9 nH costs >4%) [PEEC] |
| P02 | CIN <2 mm (MPS); "every mm matters" | Sp | **L** grows with path length × h/w | R direction, arbitrary number | same nH budget; distance only through L [PEEC] |
| P03 | Zero vias in the hot loop | Ph+Sp | **L**: through via ≈1.3 nH (1.6 mm, 0.3 mm) [C §D] | M: R for single through-vias; C for vertical loops with several short vias to L2 (SNVA803 <0.5 nH) | count nH, not vias [PEEC] |
| P04 | Solid plane on the next layer, L1–L2 ≤0.127 mm | Ph | **L** ∝ h via image currents: 1 mm×20 mm path 10 nH at h 1.5 mm, 1.9 nH at 0.1 mm [C §B]; AN-139 187→13 nH | R, strongest lever | stackup term in the L model [CF] |
| P05 | Loop-area tiers ≤2/≤10/>20 mm² | Sp | **L**: area ∝ L only at fixed h and shape | M: A on 2-layer, C on thin cores | nH [PEEC] |
| P06 | Vertical loop beats lateral | Ph | **L** ∝ spacing of opposite currents | R when L1–L2 thin; L +80% when board thickness doubles (EPC) | nH [PEEC] |
| P07 | SW-node copper minimal | Ph | **Cm**: i=C·dv/dt; 50 mm² over 0.1 mm = 19 pF → 114 mA at 6 V/ns; CV²f loss only 1.4 mW at 12 V, 500 kHz [C §P] | R for EMI coupling; loss argument X | fF to each victim and to "world" (edge, heatsink, cable) [2D] |
| P08 | Cool through PGND/EP, not SW copper | Ph | **Th** vs **Cm**: the quiet node can be large | R | thermal network with SW area capped [TN] |
| P09 | SW copper on one layer only (BQ25895) | Ph | **Cm** doubles, **M** to inner layers | R | Cm budget [2D] |
| P10 | FB/VOS Kelvin at COUT, away from SW/L | Ph | **R** of shared path; **M**, **Cm** into a 100 kΩ node | R; no vendor mm (none needed) | IR error + fF + nH coupling vs feedback-noise budget [PEEC] |
| P11 | One AGND–PGND tie at the EP | Ph | **M** (shared-branch Z=R+jωL carrying hot current) | R; literal star of traces adds L [I] | zero hot-loop current through quiet return: graph + Z_shared·I [PEEC] |
| P12 | Inductor dot on SW | Ph | **Cm** of outer winding to world | R for one measured part (8 dB) | per-part data [LU] |
| P13 | No copper under inductor (Rohm) vs keep L2 GND (TI) | Ph | **M**: eddy loss and L drop vs shielding of leakage flux | CT; depends on core leakage and f | magnetostatic of part over plane [FEM] |
| P14 | CIN/COUT grounds 1–2 cm apart (Rohm) vs common return | Ph | **M**: HF loop current through COUT ground | CT | Z_shared at ring frequency [PEEC] |
| P15 | ≥1 via per amp | Sp | **R**/**Th**: barrel 1.1–1.6 mΩ, 160–230 K/W; cross-section = 0.5–0.7 mm of 1 oz trace [C §I] | C for heating; right order for loop L | n ≥ max(I/I_via(ΔT), L target) [CF] |
| P16 | Snubber at the switch pins | Ph | **L** of snubber loop ≪ ring L | R | include in nH budget [SP] |
| P17 | Flyback: no loop inside another | Ph | **M** ∝ shared flux | R | mutual between hot and quiet loops [PEEC] |
| P18 | Drain copper minimal | Ph | **Cm**·dv/dt (hundreds of V/ns) → **Vcm** via Y-cap | R | C drain→secondary/heatsink [2D] |
| P19 | Gate driver adjacent; Kelvin source | Ph | **L**: L_G ≤ ¼(R_G+R_S)²C_GS (EPC) | R | compute L_G and common-source L [PEEC] |
| P20 | C_boot ≥10 C_g; C_VDD ≥10 C_boot | Ph | schematic: charge sharing ΔV=Q_g/C ≤10% | R | schematic check [CF] |

### PDN and decoupling ([decoupling-pdn](../rules/decoupling-pdn.md))

| ID | Rule | Orig | Physics | Verdict | Replacement [cost] |
|---|---|---|---|---|---|
| P21 | 0.1 µF per power pin | Hb+Sp | **L**, **Res**: **Z(f)** vs Z_t from L, R, C | M: excess on slow parts, short on fast | Z_t profile screener [SP] |
| P22 | Three values per pin | Hb (leaded parts) | **Res**: equal ESL gives anti-resonance; 10µ+100n+1n peaks 1.6 Ω at 129 MHz vs none for 3×10 µF (1 nH each) [C] | X | flat-profile check [SP] |
| P23 | Smallest cap closest | Hb | **L**_mount independent of value in one package | M: R only if smaller value ⇒ smaller package | lowest mounting L closest (N8) [CF] |
| P24 | Decap within 2–3 mm (or 15 mm) | Sp | **L** spreading=(µ0d/π)ln(s/a): d 0.1 mm 86→196 pH from 1.3 to 20 mm; d 1 mm 0.86→1.96 nH [C §C] | M: C on thin plane pairs, A on 2-layer/thick d | mount+spread nH vs Z_t [CF] |
| P25 | Via-in-pad, vias at pads, no traces | Ph | **L**: 0.63→0.44 nH (Axotron) | R; trades **Fab** cost | nH budget [PEEC] |
| P26 | Tight P/G plane pair | Ph | **L** spreading ∝ d; plane C 38 pF/cm² at 0.1 mm | R; plane C alone useful only >~500 MHz | PDN model [CF] |
| P27 | Derate MLCC 50% for DC bias | Ph | part choice: C(V,T) of class-2 ceramics | R | vendor model [LU] |
| P28 | Bead ≤20% rated I; check bead+C resonance | Ph | L(I) saturation; **Res** +10 dB | R | SP with bead model [SP] |
| P29 | Peak ≤1.57 Z_t | Ph | **Res** Q under repetitive load | R | PDN sweep [SP] |
| P30 | Alternate decap orientation in clusters | Ph | **M** between neighbouring loops | R, small | mutual of adjacent cap loops [PEEC] |

### High current and sensing ([high-current](../rules/power/high-current.md), [current-sense-kelvin](../rules/power/current-sense-kelvin.md))

| ID | Rule | Orig | Physics | Verdict | Replacement [cost] |
|---|---|---|---|---|---|
| P31 | IPC-2221 width (0.30 mm/A at 1 A, 10 °C) | Hb (1956 NBS tests; internal = ½ external, untested [S]) | **Th** fit I=k·ΔT^0.44·A^0.725; **R** ignored | A for IR drop: 1 A over 20 mm drops 33 mV = 3.3% of 1 V [C §F]; C internal near planes (IPC-2152) | width = max(IR budget % of rail, thermal network) [CF/TN] |
| P32 | Rohm >1 mm/A | Sp | **R**, **Th** | C except ≤1 V rails | same [CF] |
| P33 | Power traces ≥3× signal width | Hb | none | X (LearnEMC) | current-derived [CF] |
| P34 | Copper weight by dissipation (1/2/4 oz at 3/6 W) | Sp | **Th**: lateral conductance ∝ t | R order | network [TN] |
| P35 | Supply and return overlapped | Ph | **L** (laminated bus), **Vcm** | R | nH [PEEC] |
| P36 | Kelvin taps at the pad's inner edge; filter at IC | Ph | **R**: 1 oz = 0.49 mΩ/□; 1 shared □ on a 1 mΩ shunt = 49% error, +1300 ppm/K [C §K] | R, exact | sheet-current solve of tap error [2D] |
| P37 | Busbar transitions are hot spots | Ph | **R**, **Th**: 100–200 µΩ per press-fit | R | network [TN] |

### Analog, mixed-signal, precision ([analog-mixed-signal](../rules/analog-mixed-signal.md), [precision-sensing](../rules/precision-sensing.md))

| ID | Rule | Orig | Physics | Verdict | Replacement [cost] |
|---|---|---|---|---|---|
| P38 | Split AGND/DGND | Hb (datasheet legacy) | **L**, **Vcm**: split forces return detour | X except <100 kHz isolation ~1000:1 or ≥14-bit regions | partition placement; return-current overlap [PEEC] |
| P39 | ADC AGND+DGND to analog plane at the package | Ph | **M**: L·di/dt between ground pins | R | Z_shared·I_dig ≤ LSB budget [PEEC] |
| P40 | Ground strategy by ADC bits | Ph+Sp | **M**: noise ≤ LSB (12-bit/1 V: 240 µV) | R | explicit µV budget [SP] |
| P41 | Driven guard ring (fA–pA) | Ph | **Ins**: I=V/(ρ_s·squares); 5 V over 0.1 □ at 10¹² Ω/□ = 50 pA [C §L] | M: R below ~nA; harmful on fast TIAs (adds Cm) | leakage budget vs Cm budget [CF] |
| P42 | Remove pour under IN− of fast TIA; minimise summing node | Ph | **Cm**: 1 pF across 1 kΩ peaks (Williams) | R | fF budget from phase margin [2D+SP] |
| P43 | Thermocouple cold junction isothermal, symmetric | Ph | **Th** gradient × Seebeck (K: 39 µV/°C) | R | ΔT across junction pairs [TN] |
| P44 | Precision parts away from heat | Ph | **Th** drift, thermal EMF | R; distance is a proxy | gradient budget [TN] |
| P45 | Audio <100 kHz: star at entry, planned returns | Ph | **R**-dominated spread below f_x=R′/(2πL′) ≈ 0.3–1.1 MHz for 1 oz traces over h 0.2 mm [C §W] | R in regime | current solve at audio f [2D] |
| P46 | Bridge: 6-wire Kelvin, balanced traces | Ph | **R**, **Th** (copper TCR 3900 ppm/K) | R | matched-R check [CF] |

### Isolation and HV ([isolation-creepage](../rules/isolation-creepage.md))

| ID | Rule | Orig | Physics | Verdict | Replacement [cost] |
|---|---|---|---|---|---|
| P47 | Creepage table (V_RMS, PD, MG) | Lg+Ph | **Ins**: surface tracking under contamination (CTI) | R as law | lookup + surface geodesic [LU+GE] |
| P48 | Clearance from impulse voltage (OVC) | Lg+Ph | **Ins**: air breakdown under transients; 325 V/1 mm = 0.33 kV/mm vs ~3 kV/mm; Paschen min ~327 V [C §M; S] | C for steady state, sized for surges | lookup + 3-D shortest path; Paschen check at altitude/vacuum [LU+GE] |
| P49 | IPC-2221B functional spacing (0.6 mm at 31–50 V) | Mf+Hb | **Ins**, **Fab**: electrochemical migration, debris, etch tolerance; field ≤0.08 kV/mm | C electrically, R for humidity | migration risk ∝ V/gap × RH [LU] |
| P50 | Slots ≥1 mm count for creepage | Lg | **Ins**: contamination bridging | R (legal) | [LU] |
| P51 | Nothing under isolators, any layer | Ph+Lg | **Ins** through FR-4; **Cm** across barrier (CMTI) | R | pF across barrier + distance [2D] |
| P52 | ESD path corners ≤45°, arc radius <2.6 mm (TI) | Ph? | **Ins**: field enhancement during kV transients | unverified [V]; only unclamped ESD copper | 3-D electrostatic of edge [FW] |

### Thermal ([thermal](../rules/thermal.md))

| ID | Rule | Orig | Physics | Verdict | Replacement [cost] |
|---|---|---|---|---|---|
| P53 | R_θJA describes the test board | Ph | **Th** network | R | [TN] |
| P54 | ≥15.3 cm²/W two-sided (SNVA419) | Ph+Sp | **Th**: 1/(h·2A) implies h_eff 8.2 W/m²K [C §H]; fin length √(kt/2h) 21–29 mm (1 oz), 30–41 mm (2 oz) | M: A for one >~2 W source on 1 oz and in enclosures; C with airflow | fin-aware network [TN] |
| P55 | EP vias 0.3 mm at 1 mm pitch, as many as fit | Ph+Mf | **Th** 160–230 K/W each (SNVA419 261) [C §I] | R; returns diminish once via array R < spreading R | [TN] |
| P56 | Doubling copper halves lateral R; no perpendicular cuts | Ph | **Th** ∝ 1/t | R | [TN] |
| P57 | Spread hot parts 5–10 mm, avoid corners | Sp | **Th**: superposed influence fields | M | influence coefficients [TN] |
| P58 | Electrolytics, references upstream and away | Ph | **Th**: Arrhenius ×2 per 10 °C | R | part temperature [TN] |
| P59 | Tent vs don't tent EP vias | Mf | **Fab**: voiding vs wicking | CT (process) | assembly profile [LU] |

## Recommendations for our system
- Store every row as a rule record with `origin`, `basis`, `regime_predicate`, `replacement_budget` and `cost`. The LLM may cite the slogan but must emit the budget ([rule-replacements](../../ideas/physics-first/rule-replacements.md) RG1, RG10).
- Collapse P01–P06, P16, P19, P23–P25 into one ledger entry per loop, in nH, consumed by the hot-loop micro-placer N7 and decap assignment N8 ([priority agents](../../ideas/original/priority-agents-and-negotiation.md)). The distance and via rules then retire.
- Replace width-for-temperature with width = max(IR, thermal) (RG14), and copper area with a fin-aware thermal network (RG15).
- For analog nets, classify the dominant parasitic first (shared R, Cm or leakage), then choose copper (P41/P42 conflict).
- Keep isolation tables as `Lg` rules that physics may tighten but never relax.

## Conflicts and open questions
- **Same quantity, opposite rules:** P13 and P14 are M-coupling trade-offs whose sign depends on the inductor's leakage flux and the ring frequency. Only a field solve or vendor data settles them.
- **Different quantities:** P07/P08 (SW area: Cm vs Th vs R) and P41/P42 (guard copper: leakage vs capacitance). See the conflict table in [rule-basis-set](rule-basis-set.md).
- **Unverified:** TI's ESD-corner claim (P52); IPC-2221's 1956 origin and untested internal chart are [S]; the fin model ignores FR-4 in-plane conduction and radiation non-linearity.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 1–5, 9, 11, 14–18](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B, 2, 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- IPC-2221 chart history: https://pcdandf.com/pcdesign/index.php/2009-archive-articles/5731-determining-current-carrying-capacity [S]; https://design.iconnect007.com/article/114225/brooks-bits-internal-trace-temperaturesmore-complicated-than-you-think/114228/pcb [S]
- Paschen minimum: https://en.wikipedia.org/wiki/Paschen%27s_law [S]
- Primary documents as cited in the linked rule docs (AN-139, SNVA803, EPC WP010, SNVA419, MT-031, SLUP419, Bogatin/Smith/Sandler SIJ 2020).

See also: [rule-basis-set](rule-basis-set.md), [rule-genealogy-si-emi-rf](rule-genealogy-si-emi-rf.md), [rule-genealogy-routing-style-dfm](rule-genealogy-routing-style-dfm.md), [../rules/myths-and-contested.md](../rules/myths-and-contested.md)
