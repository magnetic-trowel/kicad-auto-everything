# Derivation audit table: 160 rules, one derivation each

Scope: one row per genealogy rule ([P01–P59](rule-genealogy-power-analog-thermal.md), [S01–S55](rule-genealogy-si-emi-rf.md), [R01–R46](rule-genealogy-routing-style-dfm.md)): origin, principles, one-line derivation, regime, number status, verdict. Not here: method, counts, longer derivations D1–D9 -> [derivation-audit](derivation-audit.md); quantities -> [rule-basis-set](rule-basis-set.md).
Keys: derivation table, rule rows, P01-P59, S01-S55, R01-R46, verdict, number status, principle codes

Parsed by [da_coverage.py](../../../tools/research/physics/da_coverage.py) (8 cells per row; Verdict, Num and principle codes from fixed lists): keep the format. A row counts as derived only if the derivation is correct and its regime stated. [C da §X] = [da_derivations.py](../../../tools/research/physics/da_derivations.py) section X; [C da_inductor_cutout] = [da_inductor_cutout.py](../../../tools/research/physics/da_inductor_cutout.py). Other numbers: genealogy docs and the lens named in the row (VP, CT, SY, LS, TH, IN, CD = [lens-vp](lens-vp.md) … [lens-cd](lens-cd.md)). "audit Dn" = derivation n in [derivation-audit](derivation-audit.md#nine-short-derivations).

Legend (code definitions: [derivation-audit method](derivation-audit.md#method)):
- **Origin** (genealogy classification): Ph physics, Sp simplicity proxy, Hb habit, Mf manufacturing, Mech mechanical, Lg legal, Cg cognition, Tl tool, CT contested between sources; + joins mixed origins.
- **Principles** (first = primary), code + sub-tag: P1 conservation (KCL, topo, world); P2 variational (energy, Foster, surface, elastic); P3 reciprocity/symmetry (image, lead, mode, gauge, wedge, aperture); P4 locality/scales (Z/Z0, θ, ℓm, screen, homog, ωτ); P5 dissipation/fluctuation (Q, noise, WF = WF, joule); P6 information (margin, VOI, prior); P7 extremes and accumulation (damage, principle D: [audit](derivation-audit.md#what-does-not-derive-and-principle-d)); MP manufacturing process; LG legal/standard; CG cognition/tools.
- **Num:** derived (from principles and constants), instance (budget at one typical regime), data (material, part, process, standard), arbitrary (no derivation), — (no number).
- **Verdict:** derivable, derivable-with-regime, convention, legal, habit-wrong (derivation contradicts the rule as stated), not derivable.

## Switching converters (P01–P20)

| ID | Rule | Origin | Principles | Derivation (one line) | Regime | Num | Verdict |
|---|---|---|---|---|---|---|---|
| P01 | Hot loop smallest; place it first | Ph | P2 energy; P4 Z/Z0; P5 Q; P6 margin | L = μ0·h·N□ (field energy sits in gap); Z = V/I ≈ 1 Ω ≪ Z0 so ε_L = θ·Z0/Z ≈ 0.5 [C da §E]; copper Q = h/δ cannot damp ring; "first" = least slack | L·di/dt ≳ 0.1 of V_DS margin (≳ 0.5 A/ns) | — | derivable-with-regime |
| P02 | CIN < 2 mm; every mm matters | Sp | P2 energy | series path: dL/dℓ = μ0h/w ≈ 63 pH/mm at h 0.1 mm, w 2 mm [C da §F], linear in distance; ~6× more per mm on a 1.5 mm two-layer board | one stackup (h/w) per number | instance | derivable-with-regime |
| P03 | Zero vias in the hot loop | Ph+Sp | P2 energy | via L ≈ 0.2·ℓ_v(ln(4ℓ_v/d)+1) nH: 1.3 nH through 1.6 mm, ~0.03 nH to an L2 0.1 mm down; a short via that folds loop over L2 lowers total L | through-vias vs short vias to a close L2 | — | derivable-with-regime |
| P04 | Solid plane on the next layer; L1–L2 ≤ 0.127 mm | Ph | P2 energy; P3 image; P4 Z/Z0; P5 Q | image sits at depth h: L = μ0h·N□ ∝ h and Z0 ∝ h falls toward V/I (AN-139 data: [hot-loops](../rules/power/hot-loops.md#measured-loop-inductance-vs-plane-distance)); thin gap also lowers copper Q = h/δ | edge band f ≫ R_s/(2πμ0h), always true for ns edges | instance | derivable |
| P05 | Loop-area tiers ≤ 2/10/20 mm² | Sp | P2 energy; P3 image | over a plane self-L = μ0h × squares (area aligns only 0.69 with PEEC direction, IN); area × h = image quadrupole moment: far coupling ∝ (A_a·h)(A_v·h)/r⁵ and DM emission (SY) | self-L: no close plane (h ≳ loop size); emission and far coupling: at fixed h | instance | derivable-with-regime |
| P06 | Vertical loop beats lateral | Ph | P2 energy | L ∝ separation of opposite currents: vertical gap = L1–L2 dielectric (~0.1 mm) vs lateral = part spacing (≥ 1 mm); EPC thickness data: [hot-loops](../rules/power/hot-loops.md#lateral-vs-vertical-loops) | thin L1–L2 | — | derivable-with-regime |
| P07 | SW-node copper minimal | Ph | P1 world; P3 image | audit D4: only charge whose field ends outside cell drives CM, I_CM = −jω·Σ C_ext·V (CT D2); over a plane node is a vertical dipole ∝ ∫V dA, coupling ∝ h^0.19 (SY D1) | dv/dt nodes; capacitance to node's own return plane is harmless | — | derivable-with-regime |
| P08 | Cool through PGND/EP, not SW copper | Ph | P5 WF; P1 world | heat through a dielectric costs capacitance: G_th/C = k/ε, so 1 K/W of FR-4 ↔ 127 pF [C da §A]; spend it on quiet node | when ½CV²f or C·dv/dt to world binds (high V) | — | derivable-with-regime |
| P09 | SW copper on one layer only | Ph | P1 world; P3 image | each extra layer adds ∫V dA facing other layers' victims and world | multilayer boards with victims on other layers | — | derivable-with-regime |
| P10 | FB/VOS Kelvin at COUT, away from SW and L | Ph | P3 lead; P4 Z/Z0 | sense where you regulate: V_err = Σ s_b·v_b over pieces shared with load current (Tellegen); a 100 kΩ node has ε_C = θ·Z/Z0 ≈ 90 [C da §E], so keep it short, narrow and off dv/dt copper | any regulator with a high-Z divider | — | derivable |
| P11 | One AGND–PGND tie at the EP | Ph | P1 topo | block–cut theorem: a region on one articulation point carries no foreign current; a neck of width w leaks ∝ w² on a flank and ∝ w⁴ at aggressor's stagnation point (CT D3) | below band where M and C bridge tie; tie at a stagnation point | — | derivable-with-regime |
| P12 | Inductor dot on SW | Ph | P1 world; P3 image | put dv/dt winding end inside: outer layer terminates inner layer's field lines, so C_ext·V comes from quiet end | needs part's winding order (dot convention) | — | derivable-with-regime |
| P13 | No copper under inductor (Rohm) vs keep L2 (TI) | Ph | P3 image; P1 topo; P4 ℓm | plane mirrors leakage field above f = R_s/(πμ0a): shields lower layers at cost of eddy loss and −ΔL. A cut-out is a ring still carrying eddy current at its rim: body-sized raises loss 1.05–1.4×, loses much shielding; only ≥ 2–3× winding radius cuts loss and ΔL to 3–50% [C da_inductor_cutout] | unshielded parts; f_sw ≫ f_hole (35–60 kHz for 2–3.5 mm holes, 1 oz) | — | derivable-with-regime |
| P14 | CIN/COUT grounds 1–2 cm apart vs common return | Ph | P1 topo; P3 lead | output error = Σ over pieces shared by commutation cycle and output-sense cycle (Tellegen); both vendors aim at no shared piece at ring frequency, one by distance, one by closing hot loop in its cell | ring band (100–300 MHz) | arbitrary | derivable-with-regime |
| P15 | ≥ 1 via per amp | Sp | P5 WF; P2 energy | audit D9: end-cooled barrel ΔT = V²/(8L0T) (Kohlrausch, WF): 0.03 K at 1 A × 1.3 mΩ, 10 K needs ~18 A [C da §A], so ~20× conservative for heating; n is set by loop L or IR; a cluster's spreading L follows its hull capacity, so vias inside hull add little (VP D3) | via between planes that stay cool | arbitrary | derivable-with-regime |
| P16 | Snubber at the switch pins | Ph | P5 Q; P2 energy | audit D6: overshoot wants L_s → 0; ring decay, emission, loss want a tuned absorber L_s·C_s ≈ L·C_oss (Den Hartog): Q ≈ 1 with C_s = C_oss, 72 vs 216 mW (TH D3) | objective: first-peak overshoot vs ring Q and loss | — | derivable-with-regime |
| P17 | Flyback: no loop inside another | Ph | P1 topo; P2 energy; P3 image | mutual = shared flux: in free space nesting maximizes it (1,060 pH); over a plane 0.1 mm down each loop closes through its image and nesting sets only sign (2.5 pH) (CT D5) | no close plane (typical two-layer flyback) | — | derivable-with-regime |
| P18 | Drain copper minimal | Ph | P1 world; P3 image | hundreds of V/ns × C(drain → secondary, heatsink, world) is displacement current that must close through Y-capacitors and LISN: I_CM = jω·C_ext·V | HV switch nodes | — | derivable |
| P19 | Gate driver adjacent; Kelvin source | Ph | P5 Q; P1 topo; P4 Z/Z0 | Q ≤ ½ needs L_G ≤ (R_G+R_S)²C_GS/4 (3.1 nH at 2.5 Ω, 2 nF) [C da §G]; a Kelvin source removes shared edge (common-source L) between power and gate cycles | fast switching | derived | derivable |
| P20 | C_boot ≥ 10 C_g; C_VDD ≥ 10 C_boot | Ph | P1 KCL | charge sharing: ΔV/V = C_g/(C_boot + C_g) = 9% at 10× | always (a schematic rule) | derived | derivable |

## PDN and decoupling (P21–P30)

| ID | Rule | Origin | Principles | Derivation (one line) | Regime | Num | Verdict |
|---|---|---|---|---|---|---|---|
| P21 | 0.1 µF per power pin | Hb+Sp | P2 energy; P4 θ | requirement is ‖Z(f)‖ ≤ Z_t = ΔV/ΔI over load's spectrum (bulk charge at low f, mounting L at high f); pin count is not a variable of Z(f) | right only by accident (~10 MHz logic, 1 nH mounts) | arbitrary | habit-wrong |
| P22 | Three values per pin | Hb | P2 Foster; P5 Q | audit D1 (Foster): an anti-resonance must lie between two distinct series resonances, limited only by loss; 10µ+100n+1n at 1 nH: 11 Ω at 130 MHz; 3 × 10 µF: no peak [C da §D] | MLCCs with mounting-set ESL; right only when ESL scaled with value (leaded parts) | arbitrary | habit-wrong |
| P23 | Smallest cap closest | Hb | P2 energy | closest site has lowest mounting loop L; with MLCCs ESL follows package and mounting, not value, so lowest-ESL part goes closest | coincides only when smaller value ⇒ smaller package | — | habit-wrong |
| P24 | Decap within 2–3 mm (or 15 mm) | Sp | P2 energy; P4 screen | spreading L = (μ0d/π)ln(s/a): 20 pH/mm at s 2 mm on d 0.1 mm, 200 pH/mm on d 1 mm [C da §F]; beyond λ(f) = v/√(ω_p² − ω²) (4–24 mm) a decap stops helping; above f_p position on modes matters (LS) | thin plane pair: weak lever; two-layer or thick d: strong | instance | derivable-with-regime |
| P25 | Via-in-pad, vias at pads, no traces | Ph | P2 energy; MP | mounting L ∝ h × squares of mount loop: Axotron data: [decoupling-pdn](../rules/decoupling-pdn.md#mounting-inductance-data); costs via fill and plating | ESL-limited band | — | derivable |
| P26 | Tight P/G plane pair | Ph | P2 energy; P4 Z/Z0; P5 Q | spreading L ∝ d; plane-pair Z0 ∝ d moves toward Z_t; cavity 1/Q = tanδ + δ/d makes Z_pk ∝ d·Q(d), so thin cores damp themselves (TH D4) | above decap SRF | — | derivable |
| P27 | Derate MLCC 50% for DC bias | Ph | (material) | class-2 C(V, T) is a ferroelectric constitutive property; no layout principle produces it | part choice | data | not derivable |
| P28 | Bead ≤ 20% rated I; check bead + C resonance | Ph | P5 Q; (material) | below its resistive band a bead is a near-lossless L that resonates with C (+10 dB): every LC needs a designed loss channel; saturation L(I) is part data | resonance check always; 20% is vendor data | data | derivable-with-regime |
| P29 | PDN peak ≤ 1.57 Z_t | Ph | P4 θ; P5 Q | audit D9: load toggling 0 ↔ ΔI at resonance has fundamental (2/π)ΔI; a high-Q peak passes only that: Z_pk ≤ (π/2)Z_t [C da §G] | Q ≫ 1 and a load that can repeat at f_res | derived | derivable |
| P30 | Alternate decap orientation in clusters | Ph | P3 image | antiparallel neighbours make mutuals negative: L_cluster = (L + Σ±M)/n | spacing ≲ mount-loop size; inductive band | — | derivable-with-regime |

## High current and sensing (P31–P37)

| ID | Rule | Origin | Principles | Derivation (one line) | Regime | Num | Verdict |
|---|---|---|---|---|---|---|---|
| P31 | IPC-2221 width (0.30 mm/A at 1 A, 10 °C) | Hb | P5 joule; P4 screen | Joule q′ = I²ρ/(wt) spreads in laminate over √(k·t_b/2h) ≈ 5 mm: ΔT ≈ q′λ/(2k·t_b) ≈ 7–8 K for 0.3 mm at 1 A [C da §A]; fitted exponents empirical (copper TCR and convection pull ΔT's exponent from ½ in opposite directions); IR drop never enters: anti-conservative for IR drop on ≤ 3.3 V rails | thermal only: isolated external trace, still air, no planes | derived | derivable-with-regime |
| P32 | Rohm > 1 mm/A | Sp | P2 energy; P5 joule | IR = R_s·ℓ·(I/w): 0.49 mV per mm of run at 1 A/mm (1 oz), so 20 mm is 1% of 1 V; heating is far below limits | binds only on ≤ 1 V rails or long runs | instance | derivable-with-regime |
| P33 | Power traces ≥ 3× signal width | Hb | — | no derivation: width follows current (IR, ΔT) or Z0, never another net's width | none | arbitrary | habit-wrong |
| P34 | Copper weight by dissipation (1/2/4 oz at 3/6 W) | Sp | P5 joule; P4 screen | lateral conductance ∝ t and fin length √(kt/2h) ∝ √t, so a source's usable area grows with t | one source, area-limited board | instance | derivable-with-regime |
| P35 | Supply and return overlapped | Ph | P2 energy; P4 Z/Z0 | laminated bus: field lives only in gap, L = μ0d·ℓ/w, and Z0 → V/I (impedance level) | f ≫ f_x | — | derivable |
| P36 | Kelvin taps at the pad's inner edge; filter at the IC | Ph | P3 lead; P3 gauge | lead field: V_sense = (1/I_L)∫J_load·E_lead dV → 0 when taps sit on load's equipotentials and sense loop shares no piece; at AC a voltage needs its loop, so route pair together and filter at IC | always | — | derivable |
| P37 | Busbar transitions are hot spots | Ph | P2 energy; P5 joule | constriction (Holm) resistance ρ/(2a) per contact spot dominates; current converges and I²R concentrates there | high current | — | derivable |

## Analog, mixed-signal, precision (P38–P46)

| ID | Rule | Origin | Principles | Derivation (one line) | Regime | Num | Verdict |
|---|---|---|---|---|---|---|---|
| P38 | Split AGND/DGND | Hb | P1 topo; P4 ℓm; P3 aperture | split = articulation point (exact DC isolation) but forces return detours (L), forms a slot aperture, feeds cable CM; a plane already confines half a return within ℓ50 = R_s/(2πμ0f): 6 mm at 10 kHz on 1 oz [C da §C] | helps only from DC to ~kHz, with nothing crossing, for ≥ 14-bit isolation | — | habit-wrong |
| P39 | ADC AGND + DGND to the analog plane at the package | Ph | P1 topo | die's grounds are one internal node; any impedance between pins puts Z·I_dig inside converter's measurement cycle | always | — | derivable |
| P40 | Ground strategy by ADC bits | Ph+Sp | P1 topo; P6 margin | Z_shared·I_dig ≤ LSB budget (12-bit/1 V: 240 µV): bits set budget, physics spend | per converter | — | derivable-with-regime |
| P41 | Driven guard ring (fA–pA) | Ph | P1 KCL; P5 noise; P4 ωτ | bootstrapping sets ΔV ≈ 0 across leakage path and input–guard C: leakage and effective C vanish within buffer's bandwidth; dielectric-loss noise 4kT·ωC·tanδ survives (1 pF beats 1 TΩ above 8 Hz, TH); on a fast TIA guard sits at a virtual ground that fails at HF, so there it adds C | ≤ nA, within guard buffer's bandwidth; harmful on fast TIAs | — | derivable-with-regime |
| P42 | Remove pour under IN− of a fast TIA | Ph | P4 Z/Z0; P2 energy | summing-node Z ≫ Z0 so ε_C = θ·Z/Z0 ≫ 1; C = εA/h puts a noise-gain zero at 1/(2πR_f·C) (1 pF across 1 kΩ peaks) | R_f·C_stray comparable to 1/bandwidth | — | derivable-with-regime |
| P43 | Thermocouple cold junction isothermal, symmetric | Ph | P5 joule | EMF = ∮S∇T·dl = Σ ΔS_k·ΔT_k over material junctions; isothermal junction pairs cancel | dissimilar metals in measuring loop | — | derivable |
| P44 | Precision parts away from heat | Ph | P5 joule; P4 screen | errors follow ∇T across a part (thermal EMF, drift); on boards smaller than ~2λ_th mean rise is board-wide | gradient budget, not distance | — | derivable-with-regime |
| P45 | Audio < 100 kHz: star at entry, planned returns | Ph | P4 ℓm; P1 topo | half a return spreads beyond x below f = R_s/(2πμ0x): 6 kHz at 10 mm, 62 kHz at 1 mm on 1 oz [C da §C]; above that a plane confines returns and a star only adds L | DC to ~10 kHz at board scale (1 oz) | instance | derivable-with-regime |
| P46 | Bridge: 6-wire Kelvin, balanced traces | Ph | P1 topo; P3 mode | 6-wire removes lead drops from both excitation and sense cycles; balanced copper (TCR 3900 ppm/K) drifts as a common mode that ratio cancels | always | — | derivable |

## Isolation and HV (P47–P52)

| ID | Rule | Origin | Principles | Derivation (one line) | Regime | Num | Verdict |
|---|---|---|---|---|---|---|---|
| P47 | Creepage table (V_RMS, PD, MG) | Lg+Ph | LG; P7 damage; P4 ωτ | tracking is irreversible damage of a wet, contaminated surface (CTI, surface τ_e); numbers are standard's | legal | data | legal |
| P48 | Clearance from impulse voltage (OVC) | Lg+Ph | LG; P7 damage; P4 screen | gas breakdown is a threshold on peak field with Paschen similarity V_b(p·d) (minimum ≈ 327 V); mains clearances see ≤ 1.6 kV/mm steady | legal; physics check at altitude or vacuum | data | legal |
| P49 | IPC-2221B spacing (0.6 mm at 31–50 V) | Mf+Hb | LG; P7 damage; MP | 0.08 kV/mm cannot break air down; electrochemical migration (time ∝ gap²/(µV), humidity) plus etch and debris margins set table | uncoated, humid, biased | data | legal |
| P50 | Slots ≥ 1 mm count for creepage | Lg | LG | narrow grooves fill with contamination and bridge; width is standard's X value | legal | data | legal |
| P51 | Nothing under isolators, any layer | Ph+Lg | P1 world; P3 image; LG | copper under barrier adds C across it, so CMTI displacement current I = C·dv/dt flows; it also shortens solid-insulation path (DTI, legal) | isolated domains | — | derivable |
| P52 | ESD path corners ≤ 45°, radius ≥ ~2.6 mm (TI) | Ph | P4 screen; P3 wedge; P7 damage | audit D9: isolated feature at V has surface field ≈ V/r; air (3 kV/mm) breaks down for r < V/E_bd = 2.7 mm at 8 kV (Peek: 1.5 mm) [C da §G]; near a conductor E ≈ (V/g)(g/r)^(1/3) | unclamped copper before TVS | derived | derivable-with-regime |

## Thermal (P53–P59)

| ID | Rule | Origin | Principles | Derivation (one line) | Regime | Num | Verdict |
|---|---|---|---|---|---|---|---|
| P53 | R_θJA describes the test board | Ph | P5 joule; P2 energy; LG | T = ΘP is a property of whole linear network, here JEDEC board | always | — | derivable |
| P54 | ≥ 15.3 cm²/W two-sided (SNVA419) | Ph+Sp | P5 joule; P4 screen | 1/(h·2A) implies h_eff 8.2 W/m²K; area beyond fin length √(kt/2h) (21–29 mm, 1 oz) is weakly used | one source ≳ 2 W on 1 oz or in enclosures (A); airflow (C) | derived | derivable-with-regime |
| P55 | EP vias 0.3 mm at 1 mm pitch, as many as fit | Ph+Mf | P5 WF; P2 energy; MP | each via ≈ 190 K/W, tied by WF to its 1.3 mΩ [C da §A]; parallel vias help until array R falls below spreading R | until spreading-limited | instance | derivable-with-regime |
| P56 | Doubling copper halves lateral R; no cuts across the flow | Ph | P2 energy; P1 topo | R ∝ 1/t (Thomson); a cut costs ∝ (intercepted heat flux)² and ≈ 0 along streamlines (cut-flux law, CT D1, SY D3) | always | derived | derivable |
| P57 | Spread hot parts 5–10 mm, avoid corners | Sp | P4 screen; P5 joule | mean ΔT set by board floor 1/(h·A) below ~2λ; spacing helps only local peaks; current-hogging parts want proximity (θ11 − θ12: limit 0.29 → 0.48 W from 32 to 4 mm, TH D6) | boards ≳ 2λ, non-hogging parts | arbitrary | derivable-with-regime |
| P58 | Electrolytics and references upstream and away | Ph | P7 damage; P5 joule | Arrhenius life halves per 10 °C; convective plumes are advective, so heat flows downstream (reciprocity fails in moving air) | natural or forced convection with a known flow | — | derivable-with-regime |
| P59 | Tent vs don't tent EP vias | Mf | MP; P2 surface | open vias wick solder by capillarity (Washburn: ℓ² ∝ γrt/µ) and starve joint; tented vias trap flux gas as voids; via size, fill and paste volume decide | process data | — | derivable-with-regime |

## Return paths and reference planes (S01–S14)

| ID | Rule | Origin | Principles | Derivation (one line) | Regime | Num | Verdict |
|---|---|---|---|---|---|---|---|
| S01 | Continuous reference under every fast net | Ph | P2 energy; P3 image; P4 ℓm; P1 world | above f_x return minimizes magnetic energy by riding image (50/80/94% within ±1/3/10h); a gap adds detour L and links external cycle | f ≫ R_s/(2πμ0h), = what "fast" means | — | derivable |
| S02 | Never cross splits or slots | Ph | P2 energy; P3 aperture; P1 world | detour ΔL ≈ μ0ℓ/(2 ln(4ℓ/g)) (Babinet within 6%, SY); slot is a magnetic-dipole aperture; detour links cable cycle | slots ≳ 25h; short slots and merged antipads need a solve (models disagree, IN) | — | derivable-with-regime |
| S03 | Return via within 200 mil; 50 mil at Gen5 | Ph+Sp | P2 energy | L = (μ0d/π)ln(s/a): logarithmic in s, linear in d (d 0.1 mm: 140 → 86 pH for s 5 → 1.3 mm) | pH budget per transition, per plane spacing d | instance | derivable-with-regime |
| S04 | Ott's layer-change order | Ph | P1 KCL; P2 energy; P4 screen | return changes reference too: same plane (free) < same-net planes via stitching (pH) < different nets via decaps (nH) or cavity displacement (resonant near f_p) | fast edges | — | derivable |
| S05 | Stitching cap ≤ 1 µF at split crossings | Ph | P2 energy; P4 screen | above its SRF a capacitor is its mounting L (~1 nH ≫ plane pH), so value is irrelevant; removing split is fix | above SRF | arbitrary | derivable-with-regime |
| S06 | ≥ 1.5W from voids, ≥ 90 mil from plane edge, ≥ 2h from board edge | Sp | P3 image; P4 screen | return spreads as 1/(1+(x/h)²); antenna-mode current at a plane edge ∝ 1/√((W/2)² − x²) (SY D2); so distances scale with h | expressed in h | instance | derivable-with-regime |
| S07 | Do not reference power planes | Ph | P1 KCL; P2 energy; P4 screen | return must cross between nets through decaps (5–10 nH) unless P/G cavity is thin and screened by decaps (wire medium, LS) | tight P/G (< 0.1 mm) with decaps in reach: harmless | — | derivable-with-regime |
| S08 | Review at t_r/6, terminate at t_r/2 | Ph | P4 θ; P4 Z/Z0 | errors grow with θ; critical length depends on driver R_s/Z0 and overshoot budget: t_r/6 ≈ 10% with typical drivers, t_r/2 ≥ 20% with weak ones (LS) | driver R_s/Z0 and overshoot budget | derived | derivable-with-regime |
| S09 | Terminate beyond λ/4; series R above 1 V/ns; Z ≥ Z0/4 | Hb | P4 θ | reflections matter when round trip ≳ t_r; clock's λ is wrong variable | none (wrong variable) | arbitrary | habit-wrong |
| S10 | Slow edges first; series R by default | Ph | P4 θ | trapezoid spectrum falls at 40 dB/decade above f_knee ≈ 0.35/t_r; slowing source removes content every structure would otherwise have to suppress | timing slack exists | — | derivable |
| S11 | Minimise every high-speed length | Sp | P4 θ; P3 lead | delay and loss ∝ ℓ, but emission follows overlap with antenna-mode current, ∫L_ret(x)·I dx, not length | loss- or timing-limited nets | — | derivable-with-regime |
| S12 | Stubs < min(15 mil, 0.3/Gbps) | Ph | P4 θ | quarter-wave notch c/(4ℓ√εe) must sit well above Nyquist (1.27 mm → 28 GHz) | data rate sets ℓ | instance | derivable-with-regime |
| S13 | Via-count limits (≤ 2; 0 on some SoCs) | Sp | P4 θ; P2 energy | each via is a Z step, a stub and a return transition; budget per via (RL, loss), not count | per-via budget | arbitrary | derivable-with-regime |
| S14 | Avoid power-pin corner ICs; paired P/G pins | Ph | P2 energy; P3 image | adjacent opposite currents enclose little flux: negative mutual, low package loop L | always | — | derivable |

## Crosstalk and differential pairs (S15–S30)

| ID | Rule | Origin | Principles | Derivation (one line) | Regime | Num | Verdict |
|---|---|---|---|---|---|---|---|
| S15 | 3W spacing | Sp | P3 image; P4 screen; P6 prior | K = 1/(1+(D/h)²); 50 Ω microstrip has w/h ≈ 2, so D = 3w gives K ≈ 3% on any stackup; 0.25 mm traces on 1.6 mm: 80%; stripline coupling decays as e^(−πD/b) (LS) | 50 Ω microstrip (w encodes h) | instance | derivable-with-regime |
| S16 | Reduce h before adding spacing | Ph | P3 image | inductive coupling ∝ h_a·h_v/D² (image dipoles); capacitive coupling of wide dv/dt copper ∝ ∫V dA: ~h^0.19 (2 mm strips) to h^0.74 (0.15 mm traces) (SY D1) | loops and narrow traces; not wide dv/dt copper | — | derivable-with-regime |
| S17 | Guard traces | Hb | P3 image | audit D2: at h ≪ D image already confines field; a grounded guard removes only what reaches mid-gap: −1–3% at h 0.1 mm, −48% at h 1.6 mm (D 5 mm, SY D1) | h ≳ D/3 (two-layer boards), stitched along its length | — | derivable-with-regime |
| S18 | Ground fill near traces on multilayer boards | Hb | P4 screen; P3 aperture | fill within ~2h lowers Z0 (−5.0% at gap h, −1.2% at 2h, −0.4% at 3h, thin copper; −8.4%/−2.2%/−0.8% at t = 0.35h) [C, rt_fill_z0.py]; farther, plane already holds field; unstitched fill = island resonator at c/(2ℓ√εeff) | none on multilayer boards | — | habit-wrong |
| S19 | Adjacent signal layers orthogonal | Ph+Tl | P3 image; CG | broadside coupling ∝ overlap length; an orthogonal crossing overlaps only ~w² | adjacent signal layers with no plane between | — | derivable-with-regime |
| S20 | Pairs are not self-returning | Ph | P2 energy; P3 image | with a plane closer than pair spacing each leg's field ends mostly on its own image; odd-mode return flows in plane under each leg | loosely coupled pairs over a plane | — | derivable |
| S21 | Skew ≤ min(spec, 0.1·t_r) | Ph | P3 mode | V_cm/V_d ≈ Δt/(2t_r): 0.1·t_r converts 5% to common mode | budget from receiver CMRR and EMI | derived | derivable-with-regime |
| S22 | Tighter coupling always lowers EMI; round corners remove skew | Hb | P3 mode | conversion occurs only where imbalance χ changes (V_cm = Δχ·V_dm), and driver imbalance (~1:100) bounds it; a bend adds 1.57–2p to outer leg whatever its shape | none | — | habit-wrong |
| S23 | Uncoupled ≤ 45 mil; bends ≥ 135°; equal via counts | Ph | P3 mode; P4 θ | each asymmetric section changes χ and converts; a Z step shorter than ~t_r/6 is invisible | edge rate sets length | instance | derivable-with-regime |
| S24 | Pair keep-outs 30 mil, 50 mil to clocks | Sp | P3 image; P4 screen | coupling ∝ 1/(1+(D/h)²): mils encode one h | expressed in h | instance | derivable-with-regime |
| S25 | Serpentine spread S1 < 2S; coupled switchback ≤ 1 inch per ns of t_r | Ph | P3 mode; P4 θ | a bump that spreads pair changes Z_odd and χ, so keep it < 2S; a coupled switchback whose round trip ≪ t_r/3 lets edge short-cut through NEXT and advances signal (Johnson) | timing-limited nets | instance | derivable-with-regime |
| S26 | Route 10–35° off the glass weave | Ph | P4 homog; P3 mode | a trace as wide as weave pitch is not homogenized: local εr varies along an aligned trace, and angling averages it; skew grows along lattice's strong reciprocal directions (SY) | ≳ 5 Gb/s on coarse glass | instance | derivable-with-regime |
| S27 | Loss budgets instead of lengths | Ph | P5 Q; P4 θ | attenuation = (α_c + α_d)·ℓ with α_d ∝ f·tanδ and α_c ∝ √f; budget is in dB and length is a proxy | lossy multi-Gb/s channels | — | derivable |
| S28 | AC caps ≤ 0402, plane voided under pads | Ph | P4 Z/Z0 | pad is a low-Z section (excess C); voiding plane beneath raises its Z0 back toward line's, which makes it invisible | ≳ 5 Gb/s (pad delay vs t_r) | instance | derivable-with-regime |
| S29 | Vendor skew tables differing 5–25× | Hb+Lg | P6 margin | each table hides its own margin allocation; budget derives from UI and receiver spec, table values do not | none | arbitrary | not derivable |
| S30 | DDR: match to < 20% of each limit in layout | Sp | P6 margin | a reserve for unknown driver, package and PVT terms; allocate by √(cost × sensitivity), or compute with IBIS across PVT | when other terms are unknown | arbitrary | derivable-with-regime |

## EMC (S31–S43)

| ID | Rule | Origin | Principles | Derivation (one line) | Regime | Num | Verdict |
|---|---|---|---|---|---|---|---|
| S31 | Cabled connectors on one edge | Ph | P3 lead; P3 gauge; P1 world | reciprocity: V_ab = jω∫L_ret(x)·I(x)dx with L_ret(x) = μ0h/(2π√((W/2)² − x²)) (SY D2); with both cables on one edge, little board flux links external cycle | cables that act as antennas | — | derivable |
| S32 | No high-speed circuitry between connectors | Ph | P3 lead; P1 world | same edge law: traces between cable attachment points overlap antenna-mode current | cables that act as antennas | — | derivable |
| S33 | I/O device within 2 cm; others ≥ 2 cm away | Sp | P3 lead; P4 screen | aggressor coupling into I/O nets times their lead field to cable; distance enters through its decay class | victim budget | arbitrary | derivable-with-regime |
| S34 | Group by type, high speed far from connector | Hb | P3 lead | long cross-board I/O links overlap more antenna-mode current (larger ∫L_ret·I) | none | — | habit-wrong |
| S35 | TVS at connector; no via or stub before it | Ph | P1 topo; P2 energy; P4 Z/Z0 | IC sees EMF of cycle through TVS: 3.75×10¹⁰ A/s × 1 nH = 37.5 V; clamp node's Z ≈ 0.3 Ω ≪ Z0 so ε_L dominates [C da §E] | always | — | derivable |
| S36 | CMC/filter within 5 mm of entry | Ph | P1 world; P3 lead | a filter works only at board–world cut: any C or M from inside to cable-side copper bypasses it; 5 mm proxies bypass fF | filter at a cable port | instance | derivable-with-regime |
| S37 | Stitch every λ/20; perimeter vs distributed | Sp+CT | P4 screen; P2 energy; P5 Q | audit D8: via lattice = wire medium, k_p² = 2π/(a²(ln(a/2πr) + 0.53)), independent of d; below cut-off 11–19 dB per pitch at any f; λ/20 puts f_p ≈ 6·f_max [C da §B]; perimeter-only lifts f₁ only 1.5–1.7×; vias reflect, do not damp (TH) | f_p > f_max (a ≲ λ/4); pitch from isolation distance | instance | derivable-with-regime |
| S38 | 20-H | CT | P4 screen; P3 image | fringing extends ~h, so recessing a plane by 20h barely changes edge fields and shifts cavity modes instead | none | arbitrary | habit-wrong |
| S39 | One solid ground; no I/O island on a single-point tie; no ferrite in ground | Ph | P1 world; P1 topo | any impedance in return between cable references puts Z·I into CM cycle; at HF a single-point tie is antenna feed (CT D3) | above ~kHz (ℓ50 < region size) | — | derivable |
| S40 | Chassis bond: many caps at HF, one LF path | Ph | P1 topo; P4 ℓm | choose cycle space per band: a tree at LF (external flux drives no loop current), a mesh at HF (short cycles); capacitors make topology band-dependent | all bands; chassis-bonded boards | — | derivable |
| S41 | 4 layers radiate ~15 dB less than 2 | Ph | P3 image | DM moment with its image ∝ I·A·h, and MREMC L_ret ∝ h: 20 log(1.5/0.2) = 17.5 dB | same layout, h ratio | derived | derivable |
| S42 | Spread-spectrum clocking | Lg+Ph | LG; P4 θ | Parseval: energy unchanged; a 120 kHz RBW sees 10 log(Δf/RBW) less peak: 9 dB at harmonic 1 and 16 dB at harmonic 5 for 1% at 100 MHz [C da §G] | detector-defined compliance | — | legal |
| S43 | Optional footprints (filters, TVS, shields) | Ph+Cg | P6 VOI | a real option: value = E[best action after learning] − best action now ≥ 0; large when enclosure and cable are unknown (33–84% of VOI, IN) | Vcm uncertain at layout time | — | derivable |

## RF and crystals (S44–S55)

| ID | Rule | Origin | Principles | Derivation (one line) | Regime | Num | Verdict |
|---|---|---|---|---|---|---|---|
| S44 | Field-solved 50 Ω; only ground under RF on every layer | Ph | P4 Z/Z0; P3 image | at Z0 = Z line is a pure delay at any length (ε_L = ε_C = θ); other conductors within ~3h shift Z0 or convert modes | RF lines | — | derivable |
| S45 | Match at the pin; shunt grounded via the named VSS pin | Ph | P1 topo; P3 gauge | matching network is a cycle: shunt's ground path L is in series with it, and cycle must close where IC's return does | RF matching | — | derivable |
| S46 | Arcs or 135° on RF lines | Ph | P4 θ | corner excess C ~ εw²/h gives ‖Γ‖ ∝ f·h, reaching −20 dB near 3–4 GHz·mm/h | f·h ≳ 3 GHz·mm (2.4 GHz on h ≈ 1.5 mm) | — | derivable-with-regime |
| S47 | "50–60% optimal miter" | Ph | P4 Z/Z0 | a corner vanishes to first order when its excess L/C ratio equals Z0² (ε_L = ε_C); mitering trims excess C to that point; Douville–James M = 52 + 65·e^(−1.35W/h) % gives number | W/h ≥ 0.25 | data | derivable-with-regime |
| S48 | Via fence ≤ λ_g/20 | Sp | P4 screen | audit D8: one row = inductive grid, X/η = (a/λ)ln(a/2πr), leaking ≈ 2X/η: −19 dB per row at λ_g/20, −9 dB at λ_g/10 [C da §B] | 1-D fence (here a/λ matters, unlike a 2-D lattice) | derived | derivable-with-regime |
| S49 | Antenna keep-out polygon | Ph+Lg | P4 screen; P3 image; LG | conductors inside reactive near field (≲ λ/2π, Chu radius) change antenna's currents and match; modular approval fixes environment | antennas | data | derivable |
| S50 | RF ↔ SMPS ≥ 20 mm | Sp | P3 image; P4 screen | coupling at harmonics falls by decay class (dipole 1/r³ off-plane, image quadrupole over a plane); 20 mm itself is not derived | victim budget | arbitrary | derivable-with-regime |
| S51 | Crystal ≤ 12 mm, same side; ≥ 2–2.7 mm from the chip | Sp | P2 energy; P4 Z/Z0; P5 joule | trace C of 0.07–0.10 pF/mm pulls 11–20 ppm/pF (0.8–2 ppm per mm, linear); distance from chip limits its heat and coupling | ppm and pickup budgets | instance | derivable-with-regime |
| S52 | Guard ring; no traces under crystal; no test points | Ph | P4 Z/Z0; P3 image | oscillator nodes are high-Z (~640 Ω at 25 MHz), so ε_C = θ·Z/Z0 dominates: neighbours inject through fF; a grounded ring terminates their field lines | always | — | derivable |
| S53 | Metal can grounded; copper under crystal | CT | P3 image; P2 energy | grounding can screens pickup but adds shunt C to pins (pulling); copper under adds C; sign of net benefit follows ppm vs pickup budgets | budget split | — | derivable-with-regime |
| S54 | I²C pull-up window from t_r and C_b | Ph | P1 KCL; P4 θ | t_r = 0.847·R_p·C_b (30–70%) ≤ spec; R_p ≥ (V_DD − V_OL)/I_OL | always | derived | derivable |
| S55 | Ethernet PHY ↔ magnetics ≥ 25 mm vs < 1 in | CT | P1 world; P3 lead | a trade between CM coupling from PHY region into line-side copper (C_ext) and pickup and loss on a longer MDI run; two vendor numbers meet at ~25 mm and neither derives | CM vs pickup budgets | arbitrary | derivable-with-regime |

## Geometry and routing style (R01–R14)

| ID | Rule | Origin | Principles | Derivation (one line) | Regime | Num | Verdict |
|---|---|---|---|---|---|---|---|
| R01 | No 90° corners | Hb+Mf | P4 θ; P3 wedge; P7 damage | audit D3: excess C ~ εw²/h matters only when f·h ≳ 3 GHz·mm; DC excess 0.56 vs 0.50 squares; inside corner crowds current (J ∝ r^(−1/3)), outside corner field (E ∝ r^(−1/3)): damage only (pulses t < w²/α, HV, ESD) [C da §H] | corners matter only for RF on thick dielectric, pulses, HV and ESD | — | habit-wrong |
| R02 | Route at 45° everywhere | Tl+Cg+Mf | CG | octilinear paths are 5.5% longer than any-angle on average; physics-neutral outside R01 regimes | physics-neutral band | — | convention |
| R03 | Curves / any-angle routing | Cg | CG; P3 wedge; P7 damage | ≤ 8% shorter than 45°, no L or Z benefit at board scale; pays only where corners matter (RF bends, flex strain, HV edges) | per net class | — | convention |
| R04 | No acute angles (acid traps) | Mf | MP; P4 screen | etchant renewal stagnates in acute wedges under immersion etching; spray etching renews it | features < 0.1 mm, immersion etch, flex | — | derivable-with-regime |
| R05 | Short and direct | Sp | P2 energy; P4 θ | length lowers L, R, delay and coupling only while return stays under it; off plane L ∝ h wins ("longer over a plane beats short off it") | continuous reference under path | — | derivable-with-regime |
| R06 | Minimise vias | Sp | P2 energy; P4 θ; MP | each via costs L (0.03–1.3 nH), a stub and a plane perforation, but vias also cut mounting L and carry heat and current | per via class | — | derivable-with-regime |
| R07 | Constant width, no necking | Ph+Mf | P4 Z/Z0; P4 θ | a neck is a Z step whose reflection scales as Γ·(2ℓ_n/(v·t_r)), invisible when shorter than ~t_r/6 | RF and fast edges | — | derivable-with-regime |
| R08 | Width by net class (signal 0.15–0.25 mm, power wider) | Sp+Cg | CG; P4 Z/Z0; P5 joule | width should come from a Z0 target or an IR/thermal budget; classes approximate those | where no budget binds | instance | convention |
| R09 | Wide = low inductance | Sp | P2 energy | over a close plane L′ = μ0h/w (field in gap); off-plane L ∝ ln(1/w), so 16× wider buys only −48% | w ≫ h with a close plane | — | derivable-with-regime |
| R10 | Route over the plane even if longer | Ph | P2 energy | L ∝ h·ℓ/w: a long path at small h beats a short path at large h | any net with a return | — | derivable |
| R11 | Layer direction bias (H/V per layer) | Tl+Ph | CG; P3 image | maximizes router channel capacity; physics enters only between adjacent signal layers with no plane between (S19) | physics-neutral with planes between | — | convention |
| R12 | Neat parallel bus routing | Cg | CG; P3 image; P4 θ | neatness is review value; backward crosstalk saturates beyond a coupled length v·t_r/2 while forward crosstalk grows with length, so long tight buses cost coupling | physics-adverse when spacing < ~3h over long runs | — | convention |
| R13 | Length-tune with serpentines | Ph | P4 θ; P3 mode | equalize delay when timing-limited; self-coupling (S25) and loss are costs | timing-limited nets | — | derivable-with-regime |
| R14 | Traces ≥ 2h from board edge; copper ≥ 0.2 mm from a routed edge | Ph+Mf | P3 image; MP | edge fields fringe past edge and antenna-mode current peaks there (Maxwell strip); routing tolerance is ±0.2 mm | all boards | instance | derivable |

## Vias and fan-out (R15–R24)

| ID | Rule | Origin | Principles | Derivation (one line) | Regime | Num | Verdict |
|---|---|---|---|---|---|---|---|
| R15 | No vias in hot loop, RF line, ESD path, crystal lines | Ph | P2 energy; P4 Z/Z0 | one slogan, four budgets: nH (hot loop, ESD), Γ and stub (RF), fF (crystal) | per class | — | derivable-with-regime |
| R16 | One via per power pad, never shared | Ph | P1 topo; P2 energy | a shared via is a shared edge: both pins' di/dt flow through its L and couple | fast BGA power | — | derivable-with-regime |
| R17 | Dog-bone at ≥ 0.8 mm pitch; via-in-pad below | Mf+Ph | MP; P2 energy | a dog-bone needs room for a via plus clearances between pads; below ~0.8 mm only VIP fits, and VIP also lowers L | BGA and QFN escape | data | derivable |
| R18 | Teardrops | Mf+Ph | MP; P3 wedge; P7 damage | drill breakout at a junction narrows conductor (margin vs drill σ); neck's re-entrant corners concentrate stress, σ ∝ r^(−0.46) (Williams) [C da §H], under flex and thermal cycling | HDI, flex, small rings | — | derivable-with-regime |
| R19 | Annular ring ≥ fab minimum | Mf | MP; P6 margin | breakout probability Q(ring/σ_reg): margin z·σ, with z from defect's cost ratio | fab's registration σ | data | derivable |
| R20 | Via aspect ratio ≤ 10 (or 8) | Mf | MP; P4 screen; P7 damage | plating current along hole sees electrolyte resistance vs electrode polarization (Wagner number): deposition decays toward mid-barrel when hole is deeper than its screening length; thin mid-barrel copper cracks in thermal cycling | process capability | data | derivable |
| R21 | Tent/plug policy; no open via in pad | Mf | MP; P2 surface | an open via wicks solder by capillarity (Washburn) and starves joint | reflowed pads with vias | — | derivable |
| R22 | Merged antipads form slots | Ph | P3 aperture; P2 energy | a row of touching antipads acts as one slot: aperture polarizability ∝ size³ (Bethe), so one long slot ≫ many small holes; plus return detour L | fast nets crossing via fields | — | derivable |
| R23 | Remove non-functional pads | Ph+Mf | P4 Z/Z0; P4 θ | NFPs add capacitance to barrel (lower via Z) and load stub | ≳ 5 Gb/s | — | derivable-with-regime |
| R24 | KiCad stitching default max(2 mm, 2× via) | Tl | CG; P4 screen | a tool default; physics gives pitch from f_p > f_max and isolation distance (S37) | tool default | arbitrary | convention |

## Pours, planes and reliefs (R25–R35)

| ID | Rule | Origin | Principles | Derivation (one line) | Regime | Num | Verdict |
|---|---|---|---|---|---|---|---|
| R25 | Thermal reliefs on plane connections | Mf | MP; P5 WF; P4 screen | audit D7: WF: ΔR_el = ρk·ΔR_th (37 K/W ↔ 0.25 mΩ). Hand/wave: relief cuts joint's drain 1.8–4.2×. Reflow: pad couples ~0.1 mW/K to oven vs 27–54 mW/K through spokes, follows plane either way; decoupling it would cost ≥ 66 mΩ [C da §A] | hand, wave and THT soldering on planes | — | derivable-with-regime |
| R26 | Direct-connect thermal and power pads | Ph | P2 energy; P5 WF | a direct connection minimizes R, L and R_th together (WF links last two) | reflowed SMT and press-fit | — | derivable |
| R27 | Pour all unused copper (two-layer) | Ph | P2 energy; P1 topo | a stitched, continuous pour becomes return plane: minimum magnetic energy puts return under trace; it can still raise a coupling, which is an interaction term (CD D2) | two-layer; stitched and continuous | — | derivable-with-regime |
| R28 | Ground fill on multilayer | Hb | P4 screen; P3 aperture | beyond ~2h plane already holds field (Z0 −1.2% at 2h, −0.4% at 3h for thin copper) [C, rt_fill_z0.py]; floating islands resonate | none on multilayer boards | — | habit-wrong |
| R29 | No floating or isolated copper | Ph+Mf | P3 aperture; P1 world; MP | a floating island resonates at c/(2ℓ√εeff), bridges capacitively between nets it overlaps and charges up (ESD); copper balance | island ≳ λ/10 at f_max, or overlapping aggressor and victim | — | derivable-with-regime |
| R30 | Hatched vs solid planes | Hb+Mech | P4 homog; MP; P7 damage | hatch pitch ≪ h is homogenized (Z0 near solid); pitch ≳ h shifts Z0 and return; hatching lowers bending stiffness and strain in flex | flex circuits | — | derivable-with-regime |
| R31 | Copper balance, thieving | Mf | MP; P2 elastic | plating current density follows local copper density; asymmetric copper bows board (bimetal CTE mismatch) | all fabs | — | derivable |
| R32 | Plane necks; length:width ≤ 3:1 | Ph | P2 energy; P1 topo | a neck adds ℓ/w squares of R and μ0h·ℓ/w of L and pays cut-flux price; 3:1 itself has no derivation | high-current or low-L paths | arbitrary | derivable-with-regime |
| R33 | Pour clearance > track clearance; no slivers | Mf | MP | slivers have little adhesion area and lift or break off in etch | all fabs | — | derivable |
| R34 | Big pours for power | Ph | P2 energy; P1 world | Thomson: added copper never raises a self term such as R (monotone); on switching nodes added area adds C_ext·V, and couplings can rise (interaction terms, CD D2) | quiet nets only | — | derivable-with-regime |
| R35 | Round inside corners of power pours | Ph | P2 energy; P3 wedge; P7 damage | rounding saves ≤ 0.07–0.3 squares, so loss barely moves; removes J ∝ r^(−1/3) crowding, which matters because damage is local (audit D3) | pulses with t < w²/α (0.8 ms at 0.3 mm), fusing | — | derivable-with-regime |

## DFM, assembly and placement method (R36–R46)

| ID | Rule | Origin | Principles | Derivation (one line) | Regime | Num | Verdict |
|---|---|---|---|---|---|---|---|
| R36 | DRC at fab absolute; router at recommended + margin | Mf | P6 margin; MP | optimal margin m = z·σ sets marginal defect saving L·φ(z)/σ = marginal space cost c′: z ≈ √(2 ln(L/(√(2π)·c′σ))); absolute minimum only where space is dear, recommended + margin elsewhere | fab's σ and cost ratio | data | derivable |
| R37 | Courtyard 0.25 mm | Mf | MP; P6 margin | placement σ plus rework access | assembler's σ | data | derivable |
| R38 | Symmetric pad copper on 0201/0402 (tombstones) | Mf+Ph | MP; P2 surface; P4 screen | surface tension (2–110× gravity from 1206 to 01005; Bond number ≪ 1) torques part toward whichever pad wets first; wetting time follows each pad's thermal environment, which reliefs do not set (R25) | small parts | — | derivable |
| R39 | MLCCs 3–5 mm from a V-score, parallel to the edge | Ph+Mf | MP; P4 screen; P7 damage | depaneling bends board: surface strain t/(2R) peaks at score and decays over ~ board thickness (Saint-Venant); MLCC fracture is a threshold on strain along termination axis | depaneled boards | instance | derivable |
| R40 | Polarized parts in one orientation | Cg+Mf | CG | inspection error rate | physics-neutral | — | convention |
| R41 | Single-sided SMT if it fits | Mf | MP | a second side costs a print, place and reflow pass, plus a second reflow for side-1 parts | unless density or loop L needs second side | — | derivable-with-regime |
| R42 | Fiducials; test points 1 mm from parts | Mf | MP; P6 margin | vision needs ≥ 2–3 references to fix board's affine transform; probes need clearance | all assembly | data | derivable |
| R43 | Placement order: mechanical → anchors → templates → decaps → flow; route critical first and freeze | Cg+Tl | CG; P4 screen; P6 margin | sequential tools must fix largest-scale, least-slack decisions first (τ = budget/floor) | sequential tools | — | convention |
| R44 | Schematic-flow placement, readability | Cg | CG | review cost; correlates with short nets | physics-neutral | — | convention |
| R45 | Mounting-hole keep-outs; no high speed near holes | Ph+Mf | MP; P1 world | screw-head clearance; a plated hole is a chassis bond (world node), where chassis and CM currents enter | chassis-mounted boards | — | derivable |
| R46 | Generic "keep sensitive nets 1–3 mm from Y" | Sp | P4 screen; P3 image | distance acts only through decay class: 1/(1+(d/h)²) over a plane, 1/d³ for a magnetic dipole, ~λ_th for heat | victim budget | arbitrary | derivable-with-regime |
