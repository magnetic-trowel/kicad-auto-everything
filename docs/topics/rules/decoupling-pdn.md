# Decoupling and PDN: mounting inductance, target impedance, flat profiles

**TL;DR**
- **Mounting loop inductance sets high-frequency decoupling, not capacitor value.** That means pads, vias and depth to the plane pair. In the same package, 0.1 µF and 47 µF MLCCs have the same ESL. Implement "smallest closest" as "**lowest mounting inductance closest**".
- **"Three values per pin" is a myth.** Equal-ESL values create anti-resonance peaks. Damp with ESR or controlled-ESR bulk instead of adding decade values.
- **Target impedance Z_t = ΔV/I_transient is necessary but not sufficient.** Use only the transient share of the budget, aim for a flat profile, and keep peaks ≤1.57 × Z_t for a robust design (≤3 × is tolerated in practice). Watch for "rogue waves" from several high-Q peaks.
- **Derate MLCCs for DC bias.** Run ferrite beads at about 20% of rated current and check bead + cap resonance against f_sw.
- **No open-source PDN impedance tool was found.** A lumped-RLC screener fed with geometry-derived mounting inductance is buildable and differentiating.

## Key facts

**Myths vs reality.**
- **Archambeault**, "PCB Power Decoupling Myths Debunked" (IEEE EMC chapter 2012, [slides](https://ewh.ieee.org/r3/enc/emcs/archive/2012-10-10b_DecouplingMyths.pdf)) [P]: "It's really the inductance that matters!"
  - Use the largest C the package allows.
  - The IC draws charge from between the planes; the caps replenish it.
  - Caps deliver charge better when spread out.
  - Caps placed near each other should alternate power/ground pins; the worst case is all pins the same way.
  - Deep plane pairs have higher effective inductance; avoid long thin power/ground structures.
  - With a thick (35 mil) dielectric, "Location does matter!"
- **Bogatin, Smith & Sandler**, "The Myth of Three Capacitor Values" ([SIJ 2020](https://www.signalintegrityjournal.com/articles/1589-the-myth-of-three-capacitor-values)) [P]:
  - MLCC ESL "will be independent of its capacitance value".
  - Three values with equal ESL create "two parallel resonance peaks".
  - A 47 µF electrolytic can have ~30 nH of ESL; a 0.1 µF disc ~7 nH.
  - The series-RLC model holds "when the mounting inductance is larger than about 1 nH".
  - Place MLCCs early so they get low mounting inductance.
- **Conventional rule, still taught:** ADI MT-101 ([PDF](https://www.analog.com/media/en/training-seminars/tutorials/MT-101.pdf)) [P]: a 10–100 µF electrolytic "no more than 2 in." away, plus 0.01–0.1 µF as close as possible. VR: CONTESTED against Bogatin/Archambeault.
- **Location** ([Altium](https://resources.altium.com/p/when-does-decoupling-capacitor-location-matter-pcb)) [S]: mounting inductance is location-independent; spreading inductance is not. Location matters less on tight-plane boards and matters on 2-layer boards without planes.
- **Jim Williams AN47** ([MIT mirror](https://www.mit.edu/~6.331/an47fa.pdf)) [P]: bypassing is "by far the most common error"; "the right (wrong) combination of supply line parasitics and paralleled dissimilar capacitors can produce a resonant, ringing response".
- **LearnEMC** [P]: with power and ground planes, "no traces should be used to connect to power or ground"; use a via adjacent to the pad. Hubing calls "decoupling caps on both sides of a plane gap" not-so-good: "Don't gap the ground plane!"

**Mounting-inductance data.**
- **Axotron** ([blog](https://axotron.se/blog/inductance-of-some-decoupling-layouts/)) [S], VR VERIFIED. Setup: 8-layer board, P–G 75 µm, top-to-plane ~300 µm, bottom ~1200 µm.

  | Layout | Top side | Bottom side |
  |---|---|---|
  | 0402, 0.8 mm tracks to vias | 0.63 nH | 1.35 nH |
  | 0402 via-in-pad | 0.44 nH | 1.04 nH |
  | 0306 via-in-pad | 0.29 nH | 0.70 nH |

  - Overplated via-in-pad gives a further 15–30%.
  - Via-in-pad costs fill/plate and can thieve solder ([USPTO 7312402](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7312402)).
- **Archambeault depth table** (VR addition) [P], 0402:
  - 10 mil pad-to-via: 0.9 nH at 10 mil depth to the planes, 3.2 nH at 100 mil.
  - 50 mil pad-to-via: 1.4 → 4.6 nH over the same depths.
  - Spreading on a 10" wide plane: cap 10" from the IC = 545 pH, 1" = 154 pH. Narrow planes raise L sharply.

**Target impedance and beyond.**
- Z_t = ΔV/I_transient. Example: 1 V × 5% / 10 A = **5 mΩ**.
- Bands: the VRM covers up to ~100 kHz, board caps the middle, package/die ≳50 MHz. Board mounting inductance sets a floor ([ICD](https://www.icd.com.au/articles/TargetZ_Design007-Feb2018.pdf); [MPS](https://media.monolithicpower.com/mps_cms_document/a/i/aip_meeting-the-impedance-mask_strategies-for-pdn-design-and-optimization_r1.0.pdf); [Altium PDN guide](https://files.resources.altium.com/sites/default/files/2022-02/PDN%20Simulation%20and%20Analysis%20Guide.pdf)) [S].
- **"Target Impedance Is Not Enough"** (Smith, Sandler & Bogatin; [SIJ 2019](https://www.signalintegrityjournal.com/articles/1083-target-impedance-is-not-enough)) [P]:
  - The budget also covers VRM ripple, DC regulation, IR drop and crosstalk; Z_t gets only the transient share.
  - A flat profile below Z_t is "the basic criterion for a 'robust' PDN".
  - Each peak is a parallel RLC (f, Z_peak, Z₀, Q). With t_r <3.5 ns and resonance <100 MHz, noise is governed by Z₀, so Z₀ ≤ Z_t.
  - A square wave at resonance drives 0.64·Q × the step noise after ~Q cycles → **peak ≤ 1.57 × Z_t**. "Many successfully deployed products have a peak height as large as 3× the target impedance."
  - Several high-Q peaks excited in sequence can build a "rogue wave".
- **Other approaches:**
  - Keysight [S]: flat impedance across the band.
  - Witcher & Sandler, DesignCon 2023 [S]: add flatness metrics (Q, group delay, NISM).
  - Sandler [S]: bulk C = L/R².
  - Novak et al. [S] compared synthesis methods; a related patent uses ESR-controlled banks with ESR ≤ Z_t and N = ESR/Z_t(f) ([DC06](http://electrical-integrity.com/Paper_download_files/DC06_TF-MP3_SUN.pdf); [USPTO 6571184](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/6571184)).
- **Plane cavities:**
  - f_mn = (c₀/2√εr)·√((m/a)² + (n/b)²); f₁₀ ≈ 150/(a[mm]·√εr) GHz ≈ **720 MHz** for 100 mm FR-4 (εr 4.3).
  - Vias through hot spots couple noise; stitching and decoupling lower Q ([rftools](https://rftools.io/blog/pdn-impedance-analyzer)) [S].
  - Plane capacitance ≈ 38 pF/cm² at d = 0.1 mm, εr 4.3 [I]. Ott: plane capacitance is insufficient below ~500 MHz [P].
- **Tools:** Murata SimSurfing and KEMET K-SIM give DC-bias, temperature and frequency models with SPICE/S2P export. Both are vendor-locked [S].

**Components.**
- **MLCC DC bias** [S], not re-verified:
  - 0402/0603 X7R at 50–60% of rated V loses 30–50%; 1206/1210 lose 10–20%.
  - A 10 µF 6.3 V 0402 X5R ≈ 1.5 µF at 5 V.
  - Derate to 50% of rated voltage as a start. Delivered C can be 30–70% below nominal ([Octopart](https://octopart.com/pulse/p/breaking-down-mlcc-surprises); [Ultra Librarian](https://www.ultralibrarian.com/2026/03/05/mlcc-capacitor-selection-ulc)).
- **Ferrite beads** (ADI, [Analog Dialogue 50-02](https://www.analog.com/media/en/analog-dialogue/volume-50/number-1/articles/ferrite-beads-demystified.pdf)) [P], VERIFIED:
  - Use at ~20% of rated DC current (the rating is a temperature limit). At 50%, L drops by up to 90% (TDK MPZ1608S101A: 100 Ω → 10 Ω at 100 MHz).
  - Bead + 10 nF resonated at ~2.5 MHz: **+10 dB** at a 2.4 MHz ripple.
  - Damping on the ADP5071 example: (A) series 10 Ω in the cap path, which degrades HF bypass; (B) 10 Ω across the bead; (C) C_DAMP 1 µF + R_DAMP 2 Ω.
  - Weir ([slides](https://emcfastpass.com/wp-content/uploads/2017/04/PDN_Ferrite_Beads.pdf)) [P]: above 30–40% of rated current, L drops 50%+.
  - MT-101: 0.1 µF + 1 nH resonates at 16 MHz; damp with ~10 Ω in the line or a bead (resistive above 100 kHz).
- **Trace and via current:** see [power/high-current.md](power/high-current.md) (IPC-2221 0.30 mm/A at 10 °C; conservative via table).
- **Return stitching** (cross-ref HS/EMI):
  - TI: GND via "within 200 mil (center-to-center, closer is better)" of a reference-changing signal via; Gen5 50 mil; EMA ≥2 within 100–200 mil [P]. The 1 mm / 50 mil blog figures are secondary.
  - Stitching caps: **≤1 µF, at split crossings** (TI). VR CORRECTED the 1–10 nF / 50 mil claim.

**PDN workflow** (RPA §17) [I]. Each step is code, not LLM judgement:
1. **Rails** from BOM and datasheets: V, ΔV, I_transient (or I_max × activity), band. Z_t = fraction·ΔV/I.
2. **Model:**
   - VRM = R + L above its bandwidth;
   - MLCCs with bias-derated C, ESR and ESL;
   - mounting L from geometry (tables above);
   - plane C = εA/d plus spreading L.
3. **Check:** |Z| ≤ Z_t across the band; each peak ≤1.57 × Z_t (hard, "robust") or ≤3 × (soft); report Q per peak; warn if ≥2 peaks have Q > ~2.
4. **Fix:** same-value caps (lower ESL), ESR-chosen values, or a controlled-ESR bulk cap (C ≈ L/R²). Never pile on decade values.
5. **Cavity modes:** compute f₁₀/f₀₁ from the outline; flag clock harmonics or edges within ±10% of a mode; stitch and decouple at mode maxima (edges, corners).

**Rules** (RPA §2, §17) [I]:

| ID | Rule | Numeric | Check | Sev |
|---|---|---|---|---|
| PDN-01 | Local HF cap per power pin, vias at the pads on the IC side | ≤2–3 mm; via-to-pad ≤0.5 mm; ≥1 via per pad (heuristic) | Nearest same-net-pair cap distance; via count and distance | S2 |
| PDN-02 | Order by mounting L; bulk anywhere local | Bulk within ~10–20 mm | Smallest package closest | S3 |
| PDN-03 | Tight power/ground plane pair | ~38 pF/cm² at 0.1 mm | Stack-up adjacency and thickness | S3 |
| PDN-04 | Cap count/values from the Z_t profile, not "0.1 µF per pin" | Z_t = ΔV/ΔI | Derated admittance sum vs Z_t | S3 |
| PDN-05 | Derate MLCCs at DC bias | 50% start | BOM V_rail/V_rated + package | S2 |
| PDN-06 | Bead only where needed; I_DC ≤20% rated; f_res = 1/(2π√(L·C)) not within ±50% of f_sw | — | BOM + datasheet L | S2 |
| PDN-08 | No plane cuts under referenced signals; stitch at layer changes | ≥1–2 GND vias near each reference-changing via | Nearest-GND-via distance; zone-void crossings | S2 |
| PDN-09 | Peak ≤1.57 × Z_t (robust) / ≤3 × (risk) | — | RLC sweep | S2 |
| PDN-10 | Flat profile, controlled-ESR damping | Q ≲ 1–2 | Q per peak | S3 |
| PDN-11 | Cavity mode vs clock/edge spectrum | f₁₀ formula | Outline + netlist clocks | S3 |
| PDN-12 | Plane pairs high in the stack, thin, no long thin necks | — | Stack-up position; neck width/length | S3 |

## Recommendations for our system
- **Build the open-source lumped-RLC PDN screener** (step list above). It is cheap enough to run per placement.
- **Rank decoupling placement by estimated mounting L** (package, pad-to-via distance, via length to the plane pair) using the [loop-inductance estimator](checkers-power.md). Alternate orientation in clusters.
- **Pre-layout BOM checks:** DC-bias derating, bead current ratio, bead resonance vs f_sw.
- **Add beads only on explicit requirement,** and always run the resonance check.

## Conflicts and open questions
- **"Smallest closest":** MT-101 (2009) vs Bogatin (2020) and Archambeault (2012). Default to mounting L; context switch for legacy designs.
- **No authoritative cap-to-pin maximum distance exists.** The mm values are heuristics; prefer the inductance estimate.
- **Not read in full:** Keysight and Novak. MLCC derating figures are secondary.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 2, § 17, § 19](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B, § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also: [checkers-power.md](checkers-power.md), [power/high-current.md](power/high-current.md), [power/class-d-audio.md](power/class-d-audio.md), [analog-mixed-signal.md](analog-mixed-signal.md)
