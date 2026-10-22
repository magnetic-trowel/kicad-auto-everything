# Lens TH: thermodynamics, dissipation, noise and irreversibility

**TL;DR**
- **Every unwanted joule needs a destination.** For rings above ~50 MHz over gaps ≥ 0.1 mm copper cannot be it: for wide copper (δ ≪ t) the copper-loss Q is h/δ, 15–170 for hot loops. Below ~30 MHz on thin cores copper is a real damper (0.1 mm, 1 oz: Q = 1.0/2.8/6.2 at 1/3/10 MHz; 25 µm cores: Q ≈ 5 at 100 MHz) [C, [rt_sheet_return](../../../tools/research/physics/rt_sheet_return.py)]. A **modal Q ledger** (1/Q = Σ 1/Q_k) tracks each mode's energy. The ring-band peak scales with Q (19.9 dB per decade) until the edge spectrum takes over, so damping Q 10–20 to ~1 buys 12–21 dB there (2–5 ns edges, ring amplitude ≈ supply) [C, [rt_damping](../../../tools/research/physics/rt_damping.py)], a lever round 1's EMI chain leaves out.
- **Dissipation is placed by mode shape and tuned, not put "as close as possible".**
  - A snubber is best tuned to the ring by its own inductance, L_s·C_s ≈ L·C_oss (Den Hartog's absorber): Q ≈ 1 at a third of the loss, 72 vs 216 mW [C].
  - Thin cores (Z_pk ∝ d·Q(d)) and edge RC terminations at open-edge mode antinodes damp plane cavities [C].
  - Low-loss laminates raise power-cavity peaks 1.7–3.3× [C].
- **Every loss is a noise source; every conductive heat path is an electrical element.**
  - 1 pF of FR-4 at a femtoampere input out-noises a 1 TΩ resistor above 8 Hz, and guarding leaves that noise [C].
  - Copper conducts 0.15 K/W per µΩ (Wiedemann–Franz).
  - 1 K/W through FR-4 costs 127 pF (k/ε) [C].
- **Electro-thermal coupling is two kinds of physics.**
  - Reciprocal thermoelectric coupling: EMF = ∮S∇T·dl, with a Peltier error ≤ S²/L0 (manganin 41 ppm, constantan 6.8%).
  - Nonlinear Joule–TCR coupling: a stability eigenvalue, on small boards mostly the board's floor; 2 W of MOSFETs runs 1.5× hotter than the cold estimate [C].
- **Loss is an L2 objective and damage is a local, high-order one,** so corners matter for pulses, HV and fusing, not steady loss (t < w²/α). One solver with complex screening maps fatigue (local) and Arrhenius ageing (board-wide) [C].

Tags: [P] primary, [S] secondary, [I] inference, [C] computed by [th_damping_ledger.py](../../../tools/research/physics/th_damping_ledger.py), [th_electrothermal.py](../../../tools/research/physics/th_electrothermal.py) or [th_dissipation_noise.py](../../../tools/research/physics/th_dissipation_noise.py) (seconds; uncalibrated). Ideas: [lens-th ideas](../../ideas/physics-first/lens-th.md).

## Key facts

### 1. Principles

The circuit limit is isothermal and lossless: one temperature and 4kTR noise per resistor, and nothing else dissipates, conducts heat or ages. Layout breaks it four ways: temperature becomes a coupled field; parasitic loss damps, heats and adds noise; heat paths become electrical paths; damage accumulates.

| # | Principle | Statement |
|---|---|---|
| TP1 | Least dissipation | Steady linear transport (DC copper current, resistive-regime return current, board heat) minimizes a quadratic dissipation form: J* = argmin ∫ρ\|J\|² subject to ∇·J = s (Thomson); Prigogine's minimum entropy production reduces to it at uniform T (for heat only to O(ΔT/T)). Self quantities are monotone (Rayleigh), transfer quantities not. Loss is self-adjoint: ∂P/∂σ = −\|E\|² at fixed current |
| TP2 | Passive, reciprocal, downhill heat | T = ΘP, with Θ symmetric and positive. No interior maxima except at sources. Convective plumes (advection) break the symmetry [I] |
| TP3 | Fluctuation–dissipation | S_v = 4kT·Re Z, S_i = 4kT·Re Y. Each loss injects its own noise: dielectric 4kT·ωC·tanδ; lossy line T_add = (L−1)T; antenna T_A = ηT_scene + (1−η)T_phys. Mode noise temperature: T_m = Σ(Q_m/Q_k)·T_k |
| TP4 | Modal energy ledger | 1/Q_m = Σ_k 1/Q_mk; channel k takes Q_m/Q_mk. P_rad = P_inj·Q_m/Q_rad. The ring-band peak ∝ Q_m. Copper alone: Q = h/δ |
| TP5 | Onsager thermoelectricity | EMF = ∮S∇T·dl = Σ_k ΔS_k·(T_k,in − T_k,out) over the loop's non-copper segments. Π = ST, so current through a segment adds R_P = S²T·R_th,diff > 0, at most R·S²/L0 |
| TP6 | Electro-thermal stability | ΔT = (I − ΘD)⁻¹ΘP₀ with D = diag(∂P_i/∂T_i). Stable iff g = ρ(D^½ΘD^½) < 1; amplification ≈ 1/(1−g). Common mode: θ11 + θ12. Hogging: θ11 − θ12 |
| TP7 | Irreversible damage | Life fraction D = Σ ∫ ḋ(T, ΔT_cyc, J, E, RH) dt ≤ 1 (Miner; Arrhenius, Coffin–Manson, Black, Peck). These rates are local high-p norms. Cycles use Λ(ω) = √(G_s/(h + jωc_s)) |
| TP8 | Exchange rates, boundaries | Metal: G_th = L·T·G_el. Dielectric: G_th/C = k/ε. The boundary (h, ε, α_solar, standoffs) moves with altitude, enclosure and sun |

**One matrix, four roles [I].** The dissipation form R (partial resistances plus dielectric conductances) sets current flow by its minimum (TP1), each Q by its ratio to stored energy (TP4), noise as covariance 4kT·R (TP3), and heat (TP2, TP6, TP7).

Round 1's PEEC holds R but used only the first role.

### 2. Derivation map, then derivations

- "Copper never damps, Q 31–173" (PW) (TP4): Holds for rings, Q = h/δ (D1); fails for plane pairs below ~30 MHz (D4).
- "Widen entries first; 31% of loss within 3 mm" (PW9) (TP1): Explained, plus a feed law (D2).
- "Snubber at the switch, R ≈ √(L/C_oss)" (XD19, PW29) (TP4): Qualified: tune it (D3).
- "Controlled-ESR damping, not more values" (PDN-10 in [decoupling-pdn](../rules/decoupling-pdn.md), XD88) (TP4): R ≈ Z0 per anti-resonance, frequency-selective.
- "Thin prepreg"; "lossy edge termination" (README P3, FE31, XD78) (TP4): Double benefit; pitch law (D4).
- "LNA at the antenna"; "guard fA inputs" (AMS-05, RG24) (TP3): Loss is noise, (L−1)T; guards leave dielectric noise.
- "261 K/W per via"; "no heatsinking through SW copper" (TP8): WF and k/ε exchange rates.
- "Isotherm-aligned parts" (TM13, DR27); manganin shunts (TP5): Loop integral; S²/L0; pad symmetry (D5).
- "R_DS(on) at 100 °C"; "spread hot parts"; emitter ballast (TP6): Eigenvalue modes (D6).
- "Electrolytics upstream and away" (P58, TH-06) (TP2, TP7): Arrhenius mean field; plumes are non-reciprocal.
- "Curves only for pulses under ~1 ms" (PW18) (TP7): t* = w²/α (D7).

**ESD vs surge.** An 8 kV IEC discharge stores 4.8 mJ, nearly all spent in the gun's 330 Ω; a 10 V clamp takes ~12 µJ, so ESD is a charge-path and L·di/dt problem ([CT](lens-ct.md)). Surge is TH: its joules arrive in 20 µs, while heat diffuses ~50 µm in copper, so the clamp absorbs them adiabatically.

**D1. Copper barely damps rings** (explains round 1's computed "Q 31–173", [power-copper](power-copper.md)). Per square of wide conductors with gap h, L = μ0·h and R = 2R_s = ωμ0δ, so Q = h/δ, independent of length and width. Round 1's 2-square loops imply h = L/(2μ0) = 0.12/0.40/1.19 mm and h/δ = 30.8/76.0/173.4 and 102.8, round 1's 31/76/173/103 by identity (same formula) [C]. Above 100 MHz δ ≤ 6.6 µm while gaps are ≥ 50 µm. By Wheeler's incremental-inductance rule, microstrip Q is within −7% to +18% of h/δ for w/h ≥ 0.5 and 0.67·h/δ at w/h = 0.25 [C, rt_sheet_return]. Real rings decay mainly through C_oss and capacitor losses (not modelled) [I].

**D2. Equal loss per e-fold near a feed** (explains "31% of loss within 3 mm of the pads").
- **The law.** Near a feed of log-radius a, φ = (I·R_s/2π)·ln(r/a); the whole current crosses each equipotential band, so every e-fold of radius dissipates I²R_s/2π. The fraction within r is ln(r/a)/(π·N□) for two feeds.
- **Check on round 1's pour.** The law gives 20/26% at r = 3/4 mm, the solve 22/29%, reproducing round 1's 31% (30.9%); the law holds until board edges confine the field (~5 mm) [C].
- **Corollary.** Doubling both feeds saves (ln 2)/π = 0.22 squares in any pour (solved: 0.24) [C].

**D3. A snubber is a tuned absorber** (sharpens XD19, PW29 and [buck](../rules/power/buck.md)'s "snubber at the switch"). At the ring frequency the branch impedance is Z_b = R_s + jZ0·(l − 1/n), with l = L_s/L and n = C_s/C_oss. It is resistive when L_s·C_s = L·C_oss. Minimizing the worst modal Q gives l* = 0.97/0.46/0.32/0.18 for n = 1/2/3/5, vs 1/n [C].

| Design (copper Q 50) | Worst Q | Q, C_oss 0.5–2× | Ring-band peak | Loss, 12 V, 500 kHz, C_oss 1 nF |
|---|---|---|---|---|
| n = 3, L_s = 0 (textbook) | 0.96 | 1.59 | −27.2 dB | 216 mW |
| n = 1, tuned (L_s ≈ L) | 1.01 | 2.72 | −27.2 dB | 72 mW |
| n = 3, L_s = L ("far") | 1.91 | — | −28.8 dB | 216 mW |

Overshoot still prefers L_s → 0 (first peak 0.57 vs 0.65 of I·Z0); ring decay and emission prefer tuning, at some cost in robustness to C_oss nonlinearity.

**D4. Thin power cores damp themselves** (extends "thin dielectric = capacitance", README principle 3). Since 1/Q = tanδ + δ/d and Z_pk ≈ Q·Z_mode ∝ d·Q(d); round 1's cavity model, 100 × 80 mm PWR–GND pair [C]:
- **Plane spacing.** |Z|_pk is 0.38/3.5/22/96 Ω at d = 0.025/0.1/0.4/1.5 mm on FR-4; the local exponent runs 1.66 → 1.08 (1.87 → 1.22 at tanδ 0.004).
- **Low-loss laminate** raises the peaks 1.7× at 0.1 mm and 3.3× at 1.5 mm.
- **Edge termination.** RC terminations every 10 mm at R_m = η0·d/(√εr·p) cut the peaks 5.5–8.5× (ideal parts) and 2.8–8× (0.5 nH ESL each).
- **Termination pitch:** they work while ωL_esl < R_m: p < η0·d/(√εr·ωL_esl), 5.8 mm at d = 0.1 mm and 1 GHz.
- **Material loss then stops mattering:** terminated FR-4 and low-loss boards agree within 2%.
- **Copper loss dominates thin cores:** δ/d = 0.10 at d = 25 µm and 0.72 GHz vs tanδ 0.02, hence the TL;DR's scope.
- **Stitching is not damping.** A shorting via reflects (moves modes, keeps their Q); a matched resistor absorbs (removes Q): only the second of these dual edge treatments is designed dissipation.

**D5. The Peltier bound** (new). Heat Π·I = S·T·I is pumped between an alloy element's terminal junctions. With the element as the only path (R_th = R/(L0·T)), R_P/R = S²/L0 (Harman's zT): 41 ppm for manganin (1.0 µV/K vs Cu [P]) and 6.8% for constantan (40.6 µV/K [S]). With 40 K/W pads, a 1 mΩ shunt sees 15 ppm or 2.5% [C].

Unequal pads (25 vs 80 K/W) add an EMF ∝ I² from Joule asymmetry: 156 ppm at 10 A in manganin, ten times the Peltier term. A metering patent asks for both junctions within 0.6 K ([US 12631667](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12631667) [S]). Symmetry cannot cancel the dissipative Peltier loss, but pad symmetry removes the I² term.

**D6. Electro-thermal stability is board-level on small boards.** Below ~2λ every θ_ij contains 1/(h_tot·A), so g ≥ Σα_iP_i/(h_tot·A): the board's conductance to ambient must exceed the summed loss slopes.

Four 0.5 W parts (α 0.6%/K) on a 60 × 40 mm board (round 1's FV solver) [C]:
- clustered: g = 0.36, rise 59.5 → 92.5 K;
- spread: g = 0.32, rise 52.7 → 77.1 K;
- the board floor alone gives g = 0.25 in both.

Parts whose current rises with T (BJTs, diodes, linear-mode FETs) fail first in the differential mode, at P·φ·(θ11 − θ12) = 1 with φ = 0.077/K. For θ_jc = 15 K/W parts [C]:
- moving them from 32 to 4 mm apart raises the hogging limit from 0.29 to 0.48 W;
- ballast (I·R_E = 10V_T) gives 3.2–5.3 W;
- a dual die gives 4.3 W.

**D7. When corners matter** (regime predicate for PW18, TM47, RG44). Inside-corner crowding is local, J ∝ r^(−1/3), and shows in temperature only while √(αt) < w: t* = w²/α_Cu is 0.8 ms at 0.3 mm, 9 ms at 1 mm, 80 ms at 3 mm. Round 1's 1 mm table (1.75× at 1 ms, < 1× at 10 ms) fits.

### 3. Convergences and synergies round 1 missed

- **The Q ledger joins five threads:** the EMI chain (trapezoids only, [fields-emi-budget](fields-emi-budget.md)), snubber BOM (PW29), cavity eigenvalues (FE26–FE28, OP16), antenna efficiency (FE51) and desense. The "eigenmodes" object needs complex frequencies and channel shares (and, with TP3, gives noise temperature).
- **Every conductive heat path is an electrical element.** Round 1 had the pieces: G/C = k/ε (PW5, S4), the heatsink as a 22 pF feed (DR28), standoffs as heat sinks (TM10) and chassis bonds (FE14), and the 261 K/W via (1.74 mΩ divided by L·T [C]). The copper thermal network *is* the DC network scaled by L·T: one factorization serves both.
- **DR3 used the fluctuation–dissipation engine without the physics.** Back-annotate real losses (R_ac(f), ωC·tanδ, ferrite Re Z, leakage) and the same `.noise` run gives the layout's own noise; SIM33's passivity enforcement becomes the second law it requires.
- **Five electro-thermal rediscoveries split.** Dissipative coupling (TM16, RG50, TM19, OP11, XD20, PW49) needs a fixed point plus an eigenvalue. Reciprocal coupling (TM13, TM14, DR27, part of LA28) is post-processing of T. TM17 and current hogging are modal.
- **Damage is one family:** XD8, XD23, XD52, PW18, TM47, TM22, FE44, TM24 and PC19 are local high-p objectives on one solve.

### 4. Transfers

| Lesson | From | To |
|---|---|---|
| Tuned absorber (Den Hartog) | Mechanical vibration | Snubbers, PDN damping links, cavity absorbers (XD81) |
| Noise temperature, Friis | RF receivers | fA electrometers: board dielectric is a lossy capacitor at 296 K |
| Harman's R_DC/R_AC | Thermoelectric metrology | Measuring R_P and pad asymmetry on the built shunt |
| Perron eigenvalue of coupling | Power-module SOA | Margin 1 − g as a placement critic |
| Absorptive, not reflective, filters | RF, PDN damping | I/O filters that would ring with the cable |
| Crowding-driven solder electromigration (~10⁴ A/cm², >10× local [S]) | Flip-chip reliability | Fine-pitch high-current pins (feed geometry sets crowding) |
| Complex screening length | Round 1's decap and heat kernels | Mission cycles: swing within ~2\|Λ\| (18 mm at 60 s), mean within ~2λ (76 mm) [C] |

### 5. What each conductor is doing, thermodynamically

The conductor record ([lens-cd](lens-cd.md)) gains six fields per piece b:

| Role | Quantity | Engine |
|---|---|---|
| Dissipates | P_b = Σ_f \|I_b(f)\|²·R_b(f) | PEEC + spectra |
| Damps | Q_m/Q_mb per mode (copper ~δ/h) | modal ledger |
| Adds noise | 4kT·R_b(f)·\|H_b→y\|² | one adjoint |
| Conducts heat | L·T/R_b, plus k/ε via its capacitances | DC network × L·T |
| Makes EMF | Σ ΔS·ΔT at material junctions | T field + BOM |
| Ages | ḋ_b(J, T, ΔT_cyc, E, RH) | DC and AC kernels |

### 6. Critique of round 1's synthesis

1. **No principle says where energy goes.** Damping appears once ("damping resistance where a resonance needs it"); Res carries Q without loss attribution; no physics critic measures Q of rings, filters or cable modes (PDN-10 covers PDN peaks only). Add principle 15: *every excited mode needs a designed loss channel that owns most of its damping, placed at an antinode and tuned.*
2. **The thesis needs a qualifier.** A lossless parasitic network rings, so minimizing alone cannot reach "invisible": some dissipation must be visible and designed, including **layout-born parts** (terminations, damping links, tuned mounting) as mandatory ECOs ([research-gaps](research-gaps.md) §4).
3. **The EMI chain omits the ring** (TL;DR: damping buys 12–21 dB at the ring band [C, rt_damping]). "Slower edges 3 dB" is a clock-harmonic figure: at the ring band, slowing the switch edge from 1.5 to 4 ns gives −8.5 dB (trapezoid edge) to −60 dB (erf edge) for +30 mW, so edge rate competes with damping ([validation-program](validation-program.md)).
4. **"Cheap away from runaway"** ([cross-workstream-synthesis](cross-workstream-synthesis.md)) understates the coupling: the 1–3 W examples in D6 sit at g = 0.16–0.54 (1.2–2.2× hotter) [C]. It also conflated reciprocal and dissipative coupling.
5. **"Spacing buys little below 2λ"** ([thermal-physics](thermal-physics.md)) holds for mean ΔT only, not for fatigue (local swing), hogging (proximity helps) or plumes ("upstream", TH-06 in [thermal](../rules/thermal.md)).
6. **Noise is absent as physics.** LII lists noise outputs ([schematic-to-physics](schematic-to-physics.md)) but no doc applies fluctuation–dissipation to layout; guards are recommended for fA inputs (AMS-05, RG24) though dielectric noise survives them.
7. **The basis set lacks dissipation destination** (Q, W, noise temperature) **and life fraction.** Gap 10 asks for lifetime but names no unit.
8. **The boundary was idealized.** At 20 km radiation does ~52% of the cooling; sunlit black mask sits ~64 K above white [C, rough].

## Recommendations for our system

1. **Modal Q ledger in `ledger.json`:** per mode f, Q, channel shares and ring-band emission; flag modes whose designed share is < 50% while excitation × Q exceeds budget.
2. **Synthesize dampers** as (R, C, L_mount, position) by mode shape, using the tuning condition, a ±2× C_oss check and a watt price.
3. **Count PDN damping in stackup synthesis:** d·Q(d) and hybrid laminates.
4. **Back-annotate losses as noisy elements and temperatures as instance TEMP,** so LII covers drift and layout noise.
5. **Critics:** electro-thermal margin g with mode-aware relations; thermoelectric loop EMF with congruence and shunt pad symmetry; a life ledger (DC and AC kernels, crowded-pin electromigration, CAF).
6. **Tag every heat path with its electrical twin** (Ω or pF).

## Conflicts and open questions

- **Round-3 corrections (2026-10-22):** copper damping scoped to rings above ~50 MHz; damping lever 12–21 dB; the Q 31–173 match is an identity ([red-team](red-team.md)).
- **Snubber tuning** assumes linear C_oss and copper Q 50; validate with vendor models and a coupon.
- **Cavity model:** PMC edges, no radiation loss; terminations need an openEMS check.
- **S²/L0 is an upper bound:** alloy Lorenz numbers reach ~1.3 L0, and S varies by lot.
- **FR-4 tanδ = 0.02 is a GHz value.** Below 1 kHz, relaxation and humidity may move it severalfold.
- **Not computed:** advection non-reciprocity, air-fluctuation thermal-EMF noise, the leakage trade (warmth cuts surface RH 6.3%/K [C] but adds drift).
- **Minimum entropy production** decided nothing beyond Thomson's theorem; it unifies rather than computes [I].

## Sources

- Novak, dissipative edge termination, IEEE Trans. Adv. Packag. 22(3), 1999 ([record](https://www.koreascience.or.kr/article/JAKO200111920896047.page?&lang=en)) [S]
- Lee and Romalis 2008, conducting-plate noise ([arXiv:0709.2543](https://ar5iv.arxiv.org/html/0709.2543)) [P]
- Benz et al. 2011, FR-4 dielectric-loss noise term, C·tanδ ≈ 0.04 pF ([arXiv:1101.0312](https://arxiv.org/pdf/1101.0312)) [P]
- Isabellenhütte Manganin, −1.00 µV/K vs Cu ([datasheet](https://hallaweb.jlab.org/tech/Detectors/public_html/manuals/data_sheets-manuals/G-I/I/ISABELLENHUETTE/MANGANIN-ISABELLENHUETTE-R.pdf)) [P]
- Cu–constantan 40.6 µV/K ([ADI AN-28](https://wcm-cce.cldnet.analog.com/media/en/technical-documentation/app-notes/an-28f.pdf)) [S]
- Harman method ([arXiv:2404.01565](https://ar5iv.labs.arxiv.org/html/2404.01565)) [S]
- Solder electromigration ([UCLA](https://www.seas.ucla.edu/ethinfilm/paper/JAP05451.pdf)) [S]
- Thomson, Onsager, Prigogine; Den Hartog, *Mechanical Vibrations* [S]
- Reused: [fe_cavity.py](../../../tools/research/physics/fe_cavity.py), [tm_board_thermal_fv.py](../../../tools/research/physics/tm_board_thermal_fv.py), [pw_sheet.py](../../../tools/research/physics/pw_sheet.py)

See also: [README](README.md) · [cross-workstream-synthesis](cross-workstream-synthesis.md) · [research-gaps](research-gaps.md) · [thermal-physics](thermal-physics.md) · [pdn-and-commutation](pdn-and-commutation.md) · lenses [VP](lens-vp.md), [CT](lens-ct.md), [SY](lens-sy.md), [LS](lens-ls.md), [IN](lens-in.md), [CD](lens-cd.md)
