<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Component priors and shared criteria (2026-11 audit decisions)

**TL;DR**
- **One overshoot criterion everywhere:** the switch-node peak V_in + overshoot ≤ 0.85 × V_abs; above V_abs itself the report carries a **block hazard**. The rule docs' "0.2 × V_DS,max" has no primary source and is dropped.
- **Cable common mode:** Ott's short-cable law is capped at the resonant cable's 2·60·I/r (knee 95 MHz for 1 m). The placer's budget is now the evaluator's own line, 2.6 µA at 100 MHz, not 5 µA.
- **MLCCs are derated for DC bias** with a field proxy V·√(C/body volume) fitted to vendor points, and get an ESR that falls with C. **Polarized capacitors** get ESL/ESR by body (tantalum case, can diameter), from vendor data.
- **Crystals:** C_L comes from the board (stated, or load caps in series + 3.5 pF stray); the term uses it behind `KAE_CRYSTAL_CL=board` until an A/B. Load-cap grounds stay **stitched into the plane**; with no plane under them, kae flags it.
- Code: [`kae.physics.criteria`](../../../kae/src/kae/physics/criteria.py), [`kae.excite.models`](../../../kae/src/kae/excite/models.py), [`priors.crystal_budget`](../../../kae/src/kae/physics/priors.py); corpus scan [`corpus_parts_scan.py`](../../../tools/research/physics/corpus_parts_scan.py).

## Overshoot

Before: the placer allowed a peak of 0.85·V_abs (V_abs a ladder prior one step above 1.25·V_in); the evaluators allowed the whole headroom V_max − V when a rating was known and 0.2 × the bus when not; the rule docs ([hot-loops](../../topics/rules/power/hot-loops.md), [checkers-power](../../topics/rules/checkers-power.md)) said "warn above 0.2 × V_DS,max (IRP §11)". For 12 V on a 30 V switch that is 13.5 V, 18 V, 2.4 V and 6 V of allowed ring.

What the sources say:
- **No primary source states 0.2 × V_DS,max.** IR AN-1135/1084/978, TI SLPA010/SLPA005, onsemi AN-4162 and Würth were searched; the rule traces only to the LLM-written interface rule packs (`research_notes/.../interface_rule_packs.md:1291`). TI SLPA005's "reduce ringing by up to 20%" is a likely origin of the number.
- **Derating against the absolute maximum is the documented practice:** ECSS-Q-ST-30-11C Rev 1, Table 6-34: V_DS "80 % of rated"; Vishay AN-1005: "a voltage derating is maintained between rated BVDSS and VDD (typically 90 % or less)"; TI SLYT465 keeps a 30 V FET's ring under 20 V and states the goal "to keep the ringing below the absolute maximum rating".
- **Past the rating the part fails:** Vishay AN-1005 (avalanche, "potential device destruction"; parts without an avalanche rating "should not be used" where they see it); TI SLVA494A (the SW pin's positive rating is where the low-side oxide breaks down). Integrated converters often state a short-transient SW rating (TPS563201 21 V for 10 ns, TPS621361 25.5 V for < 10 ns, LMR51430 38 V for < 20 ns), which is the right V_abs for a ring.

Decision (change): `criteria.overshoot_limits` everywhere, derate 0.85 (between ECSS 80% and Vishay 90%). The evaluate and wideband reports carry `overshoot_over_abs_max` (block when the rating is the part's, warn when it is the prior's) and `overshoot_over_derating` (warn); the place report carries `hot_loop_over_abs_max` when the loop estimate passes the inductance at which the ring reaches V_abs. The commutation cells in the brief now carry the switch's rating from [parts.json](../../../kae/src/kae/excite/parts.json) (`excite.V_abs`).

The methods keep their old numbers until an A/B: `KAE_SHARED_OVERSHOOT=1` makes the placer's and the critical router's hot-loop allocation use a known rating (it can loosen a 5 V boost on a 30 V switch from 0.6 nH to the 50 nH cap) and the spectral router price the shared bound. The evaluators and hazards always use the shared criterion.

Kept (PP5): V_in is the bus's nominal voltage and V_abs the next ladder rating ≥ 1.25·V_in. Against the research case (13.2 V on a 20 V part, 1.36 nH by the closed form) this gives 0.78 nH at 12 V: conservative, recorded in [place-terms §1](../../topics/physics/place-terms.md#1-one-currency).

Open: parts.json mixes DC and transient SW ratings (TPS563201 is stored as 19 V, its DC row; its 10 ns row is 21 V). The transient row should be preferred when re-extracting.

## Cable common mode

The evaluator's limit V_lim = 3.8e4/f (Ott 12-7, E = 1.257e-6·f·l·I/r, 1 m, 150 Ω, CISPR 32 B at 10 m) grew without bound. A cable with sinusoidal current cannot radiate more than a resonant dipole: broadside 60·I/r (Balanis, *Antenna Theory* §4.6), doubled by the ground reflection that 12-7 also includes. [fields-emi-budget](../../topics/physics/fields-emi-budget.md) step 5′ already wrote the cap. Decision (change): `criteria.cable_v_lim` in every user (harm, wideband, evaluate, em.spectral, kae.intent's `emission.cable_E`); `harm.cm` adds the knee harmonic to its candidates. Effect: unchanged to 95 MHz, 7.6 dB looser at 230 MHz.

PP10 (change): the placer's world-node budget was Ott's 5 µA ([tips-cm](https://hott.shielddigitaldesign.com/techtips/tips-cm.html): "less than 5 microamps" for class B on ≥ 1 m cables, no frequency). The placer prices at 100 MHz, where the same chain gives 2.64 µA and 5 µA is ~6 dB over (kicad-happy quotes Ott: "Just 5 microamps … at 100 MHz exceeds FCC Class B"). The budget is now `criteria.cable_i_lim(100 MHz)`. Human boards run 3–4 orders below it, so placements barely move.

## MLCC DC bias and ESR

Before: nominal C and 10 mΩ for every MLCC, against [decoupling-pdn](../../topics/rules/decoupling-pdn.md) PDN-05.

Physics: class-2 loss follows the DC field in the layers (Zednicek, EPCI 2019: "proportional to the DC field (V/mm) … a physically larger case size … reduces V/mm"; Murata FAQ 0005: C0G has "no DC bias characteristic"). A footprint gives the body, not the layer thickness t; at fixed permittivity C/volume ∝ 1/t², so V/t ∝ V·√(C/volume) for a part that fills its body. Model: C(V)/C = 1/(1 + (z/0.011)^1.3), z = V·√(C[F]/vol[mm³]), vol = L·W·min(W, 2.5 mm).

| Part | Model | Vendor point |
|---|---|---|
| 10 µF 0402 at 5 V | 0.20 | ~0.15 (decoupling-pdn.md) |
| 10 µF 0402 at 3.3 V | 0.30 | ~0.4–0.45 [S] |
| 10 µF 0603 at 3.3 / 5 V | 0.52 / 0.39 | ~0.55 / 0.35 [S] |
| 10 µF 0805 at 3.3 V | 0.69 | 0.68–0.88 across 3 vendors (EPCI) [P] |
| 100 nF 0402 at 3.3 / 5 V | 0.90 / 0.83 | ~0.9 / 0.8 [S] |
| 100 nF 0603 at 5 V | 0.93 | ~0.98 [S] |

[S] = typical SimSurfing-style values not re-verified here (Murata, TDK and analog.com pages were unreachable from this host). The vendor spread for one nominal part is ~2× (EPCI), so ±0.15 is the honest error. The rating, when known, is not used in the curve (higher-rated parts of the same C and body do lose less; no source gave a usable law), only to note a part biased past it. An unmarked ceramic ≤ 1 nF is taken as C0G.

ESR at self-resonance falls with C (electrodes in parallel, TDK FAQ 0038): 10 mΩ·(C/1 µF)^-1/2, clamped 2 mΩ–0.5 Ω, which gives 32 mΩ at 100 nF and 3 mΩ at 10 µF (typical vendor curves; no published fit was found). ESL stays the per-size table already in models.py. AMD UG483 quotes 0.9 nH for an 0402 including its fixture, against 0.45 nH part-only.

The same models feed the spectral router's prices (`kae.em.spectral` builds its circuit from `kae.excite.models`), so the router's objective changes too; `KAE_PART_MODELS=legacy` restores the old models for an A/B. The evaluators keep the new ones.

## Polarized ESL and ESR

Before: 4 nH and 0.3 Ω for every polarized part, radial cans included (the polarized test ran before the through-hole one).

| Body | ESL | ESR (100 kHz) | Source |
|---|---|---|---|
| MnO2 tantalum, case A/B/C/D/E/V | 1.2/1.6/2.4/2.7/2.9/2.5 nH | 3/2/1/0.5/0.5/0.5 Ω | Vishay tantalum FAQ (doc 40110) ESL table; AVX TAJ ESR maxima (A 10 µF 4 Ω … D 47 µF 0.4–1.1 Ω) |
| Polymer chip | the case's | 40 mΩ | Vishay polymer guide (5–200 mΩ), KEMET T520 (25–40 mΩ) |
| SMD aluminium (V-chip) | 4 nH | by diameter: 4 mm 1.35, 6.3 mm 0.36, 10 mm 0.08 Ω | Chemi-Con ("4nH for miniature radial"); Panasonic FK impedance |
| Radial aluminium | < 8 mm 10 nH; 8–12.5 mm 20; 16 mm 26; 18 mm 34 nH | 5 mm 0.3, 6.3 mm 0.13, 8 mm 0.15, 10 mm 0.08 Ω | TDK B41858 ("8…12.5 mm → 20 nH; 16 mm → 26 nH; 18 mm → 34 nH"); Vishay "5 nH to 25 nH"; TDK B41858 / Panasonic FR low-Z series |
| Axial aluminium | 20 nH | 0.3 Ω | Vishay range |
| THT disc / film | 7 nH | — | Bogatin et al. ("a small 0.1 uF disc … as low as 7 nH"); Murata ~10 nH at 10 mm lead; WIMA ~0.8–1 nH/mm |

"A 47 µF electrolytic ~30 nH" (Bogatin) is an upper bound ("as much as"). ESR from tan δ at 120 Hz overstates the 100 kHz value by orders of magnitude and is not used. General-purpose series run above these low-impedance ESRs.

## Crystal load capacitance

Before: S = C1/(2(C0 + C_L)²) with C_L fixed at 12.5 pF (32 kHz) and 12 pF (MHz). ST AN2867 (§3.7) recommends C_L ≥ 6 pF, "7 pF is a good compromise" for an LSE; at 7 pF the same C1, C0 give 22 ppm/pF instead of 8.

The board says what C_L it targets: the crystal's value ("12pF", "CL=9pF") or its load caps, C_L = C1·C2/(C1 + C2) + C_s (AN2867), C_s = 3.5 pF (2–5 pF, AN826; AN-1469 ~3.5 pF). `kae.circuit.structures.crystal_load` puts `C_L_pF` and its basis in the crystal structure. Corpus: see Measurements. Decision: change + A/B. The physics is settled, but a larger S weights crystals up to ~3× against decaps in the placer and the critical router, so `KAE_CRYSTAL_CL=board` (the board's C_L, else the corpus prior) is an arm; the default keeps the fixed values.

## Crystal ground scheme

Before: each load cap's ground gets its own via into the plane under it (Espressif style); the rule doc asked for a vendor switch (single tie for ST/TI MSP430, stitched for Espressif).

- **Single tie / local island:** ST AN2867 §7.1 ("a dedicated underneath ground plane, distinct from the application PCB ground plane … connected to the nearest microcontroller ground"); TI SLAA322D §3 (guard "connected to AVSS … never … to any other ground"; on 2-layer boards fill the opposite side with clean ground); AVR186 (keep cap grounds clear of USB/RS232/PWM return currents).
- **Stitched to the plane:** TI reversed its own single-tie advice in AM335x errata SPRZ360 advisory 1.0.30 ("this ground connection is a higher impedance connection … makes it easier for electrical noise to couple into the crystal circuit … may produce clock glitches"; connect "directly to the nearest PCB digital ground"); TI AM67 ("Connect all crystal circuit ground connections and ground guard connections directly to the adjacent layer ground plane"); Espressif (complete GND under the crystal, dense stitching); Microchip AN3588 ("through Vias directly"). Hubing (LearnEMC QOTW 2020-08-17): routing returns to a common point "enhances common-impedance coupling".
- **Agreed by both:** short symmetric crystal–C1–C2 loop, cap grounds close together, nothing under the crystal.

Electrically, the island protects the oscillator from foreign return currents in a ground made of traces. Over a solid plane the return current of the oscillator loop flows directly under its own traces, the plane's impedance across a few millimetres is far below a tie trace's, and the errata shows the tie itself admitting noise. Decision: no vendor selector. Over a plane kae stitches (unchanged). Where no ground plane lies under a load cap's ground pad, kae adds no via and the critical report raises `crystal_ground_no_plane` (warn) telling the LLM to tie the cap grounds once to the oscillator ground. A rare case remains: a MCU whose datasheet requires an isolated VSS_OSC (e.g. TUSB9261's "must not connect to the PCB ground plane") needs the brief to say so; kae has no field for it yet.

## Measurements

**Corpus** (`corpus_parts_scan.py` over 14,597 boards, 2026-11-03):
- 3,177 crystals; 2,334 with a load cap on both nets, 351 with C_L in their text. C_L from load caps (+3.5 pF): 32 kHz median 9.5 pF (n 249, p10–p90 6.9–14.5), MHz median 13.5 pF (n 1,494, 8.5–18.5); stated: 32 kHz 12.5 (7–12.5), MHz 18 pF (9–20). Commonest load caps: 32 kHz 12, 22, 10, 18 pF; MHz 22, 18, 10, 27 pF.
- 129,331 MLCCs; 58,500 sit between a named rail and ground. The model's bias factor over the class-2 ones: median 0.90 (p10 0.45); ≥ 1 µF: median 0.64, p25 0.44, p10 0.30. 64 MLCCs whose text states a rating sit on a rail above it.

**Evaluator movement** (human boards from the corpus under their intent-213 operating facts, `kae.excite.evaluate`, baseline bd67f8e vs this branch; u_hi ratio after/base per observer-source pair):

| Board | Total robust (typical) | Cable CM | Supply | Victim | Overshoot | Hazards |
|---|---|---|---|---|---|---|
| sparkfun micro:bit moto:bit (buck) | 49,503 → 24,404 (5,724 → 1,146) | median ×0.80 (0.41–7.5) | ×0.99 (0.96–1.07) | — | ×1.26 | 0 |
| shazmeenshz ESP32 flight controller (buck) | 174,188 → 106,765 (36,377 → 17,288) | ×0.88 (0.66–2.2) | ×1.03 (0.88–1.50) | ×1.06 (0.71–2.0) | ×1.64 | 1: U6 rings to 35.5 V over a prior 28 V rating (warn; no rating known) |
| gos2022 mb02a1 (no cell; DC open, no total) | — | ×0.64 (0.19–3.5) | ×1.00 (0.12–1.04) | ×1.00 (0.34–9.7) | — | 0 |

Reading: the cable-CM cap (PP2) lowers the dominant CM terms by 12–36% at the median, which is most of the totals' drop. The capacitor priors (PP3/PP4) change single pairs by up to 10× where a 100 nF part's ESR (10 → 32 mΩ) damps a resonance that set a supply or victim peak; medians stay within ±6%. The overshoot criterion tightens u by 1.3–1.6× (the 0.85 derating on the prior rating). The DC and heat bands do not move.

## Sources

- ECSS-Q-ST-30-11C Rev 1, Table 6-34 (FET V_DS 80%); Vishay AN-1005 (doc 90160); TI SLYT465; TI SLVA494A; TI SLPA005; datasheets TPS563201, TPS621361, LMR51430 (abs-max SW rows).
- Ott, EMC Engineering eq. 12-7 via kicad-happy emc-precompliance.md; Ott tips-cm; Balanis, Antenna Theory §4.6.
- Zednicek, EPCI "High CV MLCC DC/AC bias, ageing" (2019); Murata FAQ 0005; TDK FAQ 0038; AMD UG483.
- Vishay tantalum FAQ (40110), polymer guide (40076), aluminium parasitics note (48298); AVX TAJ; KEMET T520; Panasonic FK, FR, SP-Cap EEF-LR; TDK B41858; Chemi-Con characteristics page; Nichicon UWX; WIMA knowledge base; Murata EMI know-how 6-5-3; Bogatin, Smith & Sandler, SIJ 2020.
- ST AN2867 Rev 10 §3.7, §7.1, LSE FAQ; TI SLAA322D §3; Atmel AVR186; Microchip AN3588 §1.9; TI SPRZ360 advisory 1.0.30; TI AM67 datasheet crystal layout; Espressif ESP32-S3 PCB layout guidelines; LearnEMC QOTW 2020-08-17.
