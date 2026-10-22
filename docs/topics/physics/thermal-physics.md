# Thermal and electro-thermal physics of the board

**TL;DR**
- **A board is a 2-D fin.** Two numbers describe it. The sheet conductance G_s = Σ k·t gives the near-field slope P/(2πG_s): 5.6 K per watt per e-fold of distance on 2-layer 1 oz. The spreading length λ = √(G_s/h_total) is 38 mm on 2-layer 1 oz in still air, 46 mm on a 4-layer board with planes and 8 mm on bare FR-4. A board smaller than about 2λ is nearly isothermal plus local peaks. On such a board, spacing hot parts lowers the mean rise little; total power over total area sets the floor [C]. Spacing still moves a neighbour's peak by 10–20% (E5) and matters for fatigue, current hogging and plumes ([lens-th](lens-th.md)).
- **TI's rules decompress exactly.**
  - 15.3 cm²/W is an isothermal two-sided plate with h ≈ 8 W/m²K per side; "500 °C·cm²/W" is 1/(2h) at h = 10.
  - 261 °C/W is barrel conduction of a 12 mil via with a 17.5 µm wall through 1.6 mm.
  - SLVA959's 5.73 °C/W would need a 0.95 mm solid copper rod.
  - Our finite-volume (FV) solver needs 12.1 cm² for a 40 K rise at h = 10 [C].
- **Vias matter only when heat must change layers.** If a top pour already touches the exposed pad (EP), 9 EP vias cut the pad rise by only 13%. If the top copper is just the EP, they cut it by 58% (126 → 53 K). Going from 1 oz to 2 oz copper cuts it by 22%. A cut across the heat flow costs 20–30× as much as the same cut along it [C].
- **Placement scoring can be exact and cheap.** The heat equation is linear, so superposition is exact. A shift-invariant kernel alone underestimates by 2–3× on a 60×40 mm board. Adding a lattice of edge images brings it within about 2% of a full solve [C].
- **Electro-thermal and precision effects are the real layout drivers near sensitive parts.**
  - Copper's +0.39%/K gives ΔT = ΔT₀/(1 − αΔT₀): no steady state above ΔT₀ ≈ 254 K, so the conductor fuses.
  - 0.5–2 K/mm gradients within 10 mm of a 1 W source put tens of µV of thermocouple error across a 2-terminal part lying along the gradient.
  - Electrolytic life halves per +10 K; a 32 kHz crystal shifts −13.6 ppm at +20 K.

## Key facts

All [C] numbers come from three scripts:
- [tm_board_thermal_fv.py](../../../tools/research/physics/tm_board_thermal_fv.py): a multi-layer FV solver with via barrels and h on both faces. Defaults are k_Cu 390, FR-4 k_xy 0.8 and k_z 0.3 W/mK, 1.6 mm board, h = 10 W/m²K per side.
- [tm_thermal_analytic.py](../../../tools/research/physics/tm_thermal_analytic.py).
- [tm_solder_reflow.py](../../../tools/research/physics/tm_solder_reflow.py).

### The board as a fin

Steady state is G_s∇²T = h_total·T − q, where h_total is both faces. A point source in an infinite sheet gives T(r) = P/(2πG_s)·K₀(r/λ). That is ln-like inside λ and exponential beyond it. The FV solver matches K₀ within 4% at 5–40 mm, so it validates [C].

| Stackup (1.6 mm) | G_s (mW/K) | λ, still air (h_tot 20) | λ, forced air (h_tot 60) | K per W per e-fold |
|---|---|---|---|---|
| bare FR-4 | 1.3 | 8 mm | 5 mm | 124 |
| 2L 1 oz both sides | 28 | 38 mm | 22 mm | 5.6 |
| 2L 2 oz | 56 | 53 mm | 30 mm | 2.9 |
| 4L 1/0.5/0.5/1 oz planes | 42 | 46 mm | 27 mm | 3.8 |
| 6L all 1 oz | 83 | 64 mm | 37 mm | 1.9 |

[C], [tm_thermal_analytic.py](../../../tools/research/physics/tm_thermal_analytic.py) §C. [rule-genealogy-power-analog-thermal](rule-genealogy-power-analog-thermal.md) quotes a 21–29 mm fin length for one 1 oz layer. Ours is larger because both copper layers and in-plane FR-4 conduct; both are right for their assumptions.

**Rise at distance d from a 1 W, 3×3 mm source** on a 10×10 cm board with full planes [C, E5]:

| Board | d = 0 | 5 mm | 10 mm | 20 mm | 30 mm | 45 mm |
|---|---|---|---|---|---|---|
| 2L 1 oz | 25.8 K | 14.4 | 10.2 | 6.7 | 5.1 | 4.2 |
| 4L planes | 20.3 | 11.8 | 8.8 | 6.2 | 5.1 | 4.4 |

At 10 mm a neighbour sees 40% of the source's own rise. The ~4–5 K floor is P/(2hA_board).

### Heat-transfer coefficients

[C], [tm_thermal_analytic.py](../../../tools/research/physics/tm_thermal_analytic.py) §B, H. These are laminar natural-convection correlations for a 50 mm plate in 25 °C air, plus linearised radiation 4εσT³.

| ΔT | Vertical convection | Facing up | Facing down | Radiation, ε 0.9 (mask) | Radiation, ε 0.05 (bare/ENIG) |
|---|---|---|---|---|---|
| 10 K | 5.3 | 5.0 | 2.2 | 5.7 | 0.3 |
| 40 K | 7.6 | 7.0 | 3.1 | 6.6 | 0.4 |

- **Still-air totals are 10–15 W/m²K per side.** TI's h = 10 is a fair still-air value. A board's downward face is about half as effective.
- **Radiation is roughly half the cooling in still air.** Solder mask emits at ε ≈ 0.9–0.95; bare copper and ENIG at 0.03–0.1 ([vendor guide](https://www.allpcb.com/allelectrohub/ir-temperature-sensors-for-non-contact-pcb-testing-a-practical-guide) [S]). Stripping mask off a spreader "for cooling" loses about 40% of its h, so keep mask on spreaders [C].
- **Forced air at 1–2 m/s gives h ≈ 20–50,** which shrinks λ by about √3.

### Decompressing the TI thermal rules

| Rule ([thermal.md](../rules/thermal.md)) | Physics | Our check | Verdict |
|---|---|---|---|
| ≥15.3 cm²/W two-sided copper for 40 K | Isothermal plate: A = 1/(2hΔT) = 12.5 cm² at h = 10, or 15.2 at h = 8.2 | FV, 1 W in a 3×3 mm EP, stitched pours: 40 K at 12.1 cm² (35 mm square) [C, E1] | Physics. Valid while the pour side is < λ. Beyond ~2λ extra area does nothing; at 64 cm² the rise is still 27.6 K |
| 261 °C/W per 12 mil via | R = L/(k·π·t_p·(d−t_p)): 1.6 mm, 0.305 mm, 17.5 µm → 260 K/W [C] | 0.3 mm with 25 µm (IPC class 2/3 typical) → 190 K/W; one L1→L2 hop in 0.2 mm → 24 K/W [C] | Physics. Use the real plating and the real path length |
| "As many vias as fit" | Vias in parallel with spreading and the FR-4 column (a 1×1 mm FR-4 cell is 5333 K/W) | Top pour attached: 0→9 vias, 41.9 → 36.4 K. EP-only top copper: 126 → 97 (1 via) → 53 K (9 vias) [C, E2] | Physics, but conditional. Vias pay only when the heat must change layer |
| 1 / 2 / 4 oz by dissipation | λ ∝ √t, near-field slope ∝ 1/t | 0.5 → 1 → 2 → 4 oz: 49.8 → 35.6 → 27.6 → 23.3 K (40×40 mm pour) [C, E3]; TI: −25% for 1 → 2 oz [P] | Physics, with diminishing returns once λ exceeds the pour |
| No cuts across heat flow | Directional resistance in the flux field | 20 × 0.5 mm cut at 5 mm: across the flow +0.87 K (top layer), +1.61 K (both layers); along the flow +0.04 to +0.06 K [C, E4]; TI +5.5 vs +1.5 K [P] | Physics. Score cuts by flux·normal (TM5) |
| SLVA959 5.73 °C/W per via | Would need 0.72 mm² of copper, a 0.95 mm solid rod | [C] §A | Error, as flagged in [motor-drivers](../rules/power/motor-drivers.md) |

**Fills** [C, §A]:
- 0.3 mm, 25 µm, 1.6 mm via, epoxy-filled: 190 K/W, no gain.
- Conductive paste: 185 K/W.
- Solder-filled: 144 K/W.
- Copper-filled: 58 K/W, a 3.3× gain.
- The "6–8× better filled vias" claim ([thermal.md](../rules/thermal.md) [S]) holds only against thinner plating.

### IPC-2221/2152 as a thermal model vs a thermal network

**Where the charts come from.**
- IPC-2221's I = k·ΔT^0.44·A^0.725 descends from 1956 National Bureau of Standards (NBS) curves, which were "tentative" and poorly controlled ([PCD&F](https://pcdandf.com/pcdesign/index.php/2009-archive-articles/5731-determining-current-carrying-capacity) [S]).
- IPC-2152 re-measured traces on a 14 × 7 × 0.07 in polyimide board with no planes, then added correction factors ([Olson](https://blog.mbedded.ninja/pdfs/JackOlson-HowTo2152.pdf) [S]).

**Both charts are the same physics, fitted to one test geometry.** The trace makes heat I²ρ(1+αΔT)/(w·t) per metre. It sheds heat through a line conductance G′, which is set by the fin around it and by any plane under it.

**A line-source model reproduces IPC-2221 within 2× from first principles** [C, §D]. Widths for a 10 K rise on external 1 oz:

| Current | IPC-2221 | Bare board | Plane 0.2 mm below |
|---|---|---|---|
| 1 A | 0.30 mm | 0.16 mm | 0.11 mm |
| 2 A | 0.79 mm | 0.62 mm | 0.37 mm |
| 5 A | 2.78 mm | 3.32 mm | 1.58 mm |

Consequences:
- **A plane under the trace roughly halves the rise.** IPC-2152 found the same [S].
- **Neighbouring heat adds linearly,** which no chart captures.
- **IPC-2221's exponents are physics-plausible.** For narrow traces I ∝ ΔT^0.5·A^0.5; for wide traces I ∝ A·t^−0.5. The 0.44 exponent absorbs the TCR.
- **So use a network:** per-net line conductance from stackup and planes, plus superposed part heat, plus the TCR fixed point. The chart is the fallback (TM18).

**TCR feedback** [C, §E]. At constant current, ΔT = ΔT₀/(1 − αΔT₀) with α = 0.00393/K.
- A constant-R estimate of 40 K becomes 47.5 K; 100 K becomes 165 K.
- No steady state exists above ΔT₀ = 254 K. That is the clean physics behind fusing.
- IR drop at 40 K above ambient is 16% higher than the 20 °C value most calculators print.

### Heatsinks, interfaces and alternative paths

[C, §H]:

| Path | R |
|---|---|
| TIM pad 0.5 mm, k 3, 10×10 mm | 1.7 K/W |
| Grease 50 µm | 0.17 K/W |
| Insulating pad under a TO-220 tab | ~1.9 K/W |
| FR-4 1.6 mm under 1 cm² with no vias | 53 K/W |
| Brass M3 standoff (10 mm) to a metal chassis, including spreading into a 6 mm plated screw pad on 2L 1 oz and contacts | ~22 K/W |

- **A metal standoff is a heat sink.** At ~22 K/W it equals the convection of about 23 cm² of two-sided board at h = 10. Put hot parts near metal standoffs.
- **Package tops are poor paths.** θ_JT of plastic packages is 50–200 °C/W, so heat-sink EP parts from the board bottom ([thermal.md](../rules/thermal.md) [P]).
- **A floating heatsink is a capacitively coupled antenna.** Ground it deliberately; see [emc-placement](../rules/emc-placement.md).

### Pulsed loads: diffusion length, not area

Diffusion length is √(αt) [C, §I]:

| Time | Copper | FR-4 (through-plane) |
|---|---|---|
| 1 ms | 0.34 mm | 0.01 mm |
| 0.1 s | 3.4 mm | 0.12 mm |
| 1 s | 10.6 mm | 0.38 mm |
| 10 s | 34 mm | 1.2 mm |

For a pulse shorter than about 1 s, only copper within a few mm of the source and above the first dielectric stores the heat. Local copper mass (thicker copper, a copper coin, a local pour on the same layer) beats spreading area. Board area acts only on 10–100 s time scales.

### Placement scoring by superposition

Test case: four sources (1.0, 0.5, 0.8 and 0.3 W) on a 60×40 mm 2-layer board with planes [C, E6]:

| Source | Exact FV | Kernel only | Kernel + 1 ring of images | Kernel + 6 rings |
|---|---|---|---|---|
| 1.0 W at (10,10) mm | 79.3 K | 36.0 | 77.5 | 80.1 |
| 0.5 W at (30,20) mm | 63.8 | 25.1 | 61.9 | 64.9 |
| 0.3 W at (45,8) mm | 58.9 | 18.0 | 57.1 | 60.0 |

- **Edges are adiabatic, so mirror sources represent them.** On small boards the image lattice carries most of the answer.
- **This validates OP23** in [optimization](../../ideas/physics-first/optimization.md).
- **Non-uniform copper breaks shift invariance.** Use the kernel for proposals and one FV solve (~1 s at 0.5 mm grid, 2 layers) for accepted moves.

### Temperature-sensitive victims

| Victim | Physics | Sensitivity | Layout lever |
|---|---|---|---|
| Al electrolytic | Electrolyte loss, Arrhenius | Life ×0.5 per +10 K (Ea ≈ 0.79 eV implied); +35 K → ×0.09 [C, §F] ([CapXon](https://www.capxongroup.com/files/Lifetime%20Compendium_EN.pdf) [V]) | Keep outside the near field; budget ΔT from life (TM15) |
| 32.768 kHz crystal | Parabolic tuning-fork curve | −0.034 ± 0.006 ppm/K² around 25 ± 5 °C ([Raltron R38](https://www.raltron.com/webproducts/specs/CRYSTAL/R38.pdf) [S]); +20 K → −13.6 ppm ≈ 1.2 s/day | Board ΔT budget, not mm |
| AT-cut MHz crystal | Cubic curve, flat near 25 °C | Few ppm over tens of K | Usually not limiting |
| Voltage reference | TC (1–50 ppm/K) plus board stress | TI: "the center of a PCB generally has the highest mechanical and thermal expansion stress"; a U-slot "helps in reducing the impact of the PCB stresses" ([LM4132](https://www.ti.com/document-viewer/LM4132/datasheet/layout) [P]) | Edge or corner placement, U-slot (thermal and stress moat, TM12) |
| Thermocouple CJ, RTD, NTC sensing ambient | Measures local board T | 1 K = 1 K error | Isotherm with the junction; away from sources |
| Precision DC path | Seebeck at dissimilar junctions | Cu–Kovar ≈ 35 µV/K, Cu–solder 1–3 µV/K; thick-film resistor about 40 µV for an 8 °C difference ([Vishay FACTS #108](https://xdevs.com/doc/VPG/theremf.pdf) [P]; [Keithley](https://docs.ampnuts.ru/eevblog.docs/Keithley/Ch3_LowLevMsHandbk.pdf) [S]) | Isotherm-aligned orientation (TM13); "thermal bridges" (Vishay) |

**The thermocouple error is quantified** [C, §G]. Use 2L 1 oz planes and a 0603 (1.6 mm) lying along the gradient of a 1 W source:

| Distance | Gradient | Solder joint (3 µV/K) | Kovar pins (35 µV/K) |
|---|---|---|---|
| 3 mm | 1.9 K/mm | 9 µV | 105 µV |
| 10 mm | 0.56 K/mm | 2.7 µV | 31 µV |

Rotating the part 90° puts both terminals on one isotherm and removes the first-order term. This is the physical reason for thermally symmetric precision layouts. The same physics makes a matched pair's two inputs see equal temperatures when they straddle a symmetry axis of the heat field.

### Other electro-thermal couplings

- **Positive feedback:** silicon MOSFET R_DS(on) rises about 0.5–0.8%/K (typical datasheet curves [I]), and copper 0.39%/K. Hot copper next to a FET raises both losses.
- **Current-sense errors:** the shunt TCR (50–100 ppm/K) plus copper in the sense path (3900 ppm/K) ([current-sense-kelvin](../rules/power/current-sense-kelvin.md)).
- **Intentional coupling:** a protection NTC must sit thermally close to the part it protects. The placer needs both "repel" and "attract" thermal relations (TM17).

## Recommendations for our system

1. **Express every thermal spacing in units of λ.** Compute λ per region from the stackup and local copper fraction (§fin table). Below about 2λ, the placer stops spreading hot parts for the mean rise (it still prices neighbour peaks, and current-hogging parts want proximity). It maximises connected copper, edge exposure and metal-standoff paths, and uses moats to protect victims.
2. **THERM-DT and THERM-COUPLE** ([physics-critics-catalog](physics-critics-catalog.md)) should use the image-lattice kernel for proposals and the FV solver for accepted states. Report ΔT in K and victim drift in ppm, µV or life fraction, never in mm.
3. **Replace fixed rules with conditional physics.**
   - Via counts: compute ∂T/∂N_via.
   - Copper weight: compute ∂T/∂oz and weigh it against the fab spacing penalty (47 µm + 1.65·t; see [hv-and-manufacturing-physics](hv-and-manufacturing-physics.md)).
   - Cuts: use a flux-direction penalty instead of "no cuts".
4. **Size high-current traces with the line-conductance network and the TCR fixed point.** Keep IPC-2221 as the conservative fallback, and log which one bound.
5. **Record h assumptions explicitly in the IR `heat_path`:** orientation, enclosure, airflow, emissivity of mask vs bare copper. They move results by ±40% ([physics-ir](physics-ir.md)).

## Conflicts and open questions

- **λ definition:** ours, 38 mm on 2L 1 oz, counts two copper layers plus FR-4. [rule-genealogy-power-analog-thermal](rule-genealogy-power-analog-thermal.md) uses one layer (21–29 mm). Use the stackup-specific G_s.
- **The 15.3 cm²/W rule is conservative for one ~1 W source in our model** (26% above our FV answer). It turns anti-conservative for multi-watt sources on 1 oz and in enclosures, as [rule-genealogy-power-analog-thermal](rule-genealogy-power-analog-thermal.md) notes: in E1 the rise saturates near 27 K/W beyond 64 cm², so 3 W cannot meet 40 K on any 1 oz area.
- **The FV solver is steady-state and 2.5-D.** It ignores package θ_JC, contact resistance, enclosure air temperature rise and non-uniform h. Validate against an IR camera (emissivity-corrected) or Elmer FEM (GPL/LGPL, run as a separate process; licence to be confirmed) before trusting absolute values.
- **IPC-2152 charts were not read** (paywalled). The line-source model is first-order.
- **The thermocouple coefficients for resistor terminations are vendor-level.** Kovar vs copper ranges from 35 to 75 µV/K across sources.

## Sources

- research notes: [rules_power_rf_analog_dfm.md § 5, § 11, § 14, § 18](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- TI SNVA419C, SPRA953D, SLMA002H, SLVA959B via [thermal.md](../rules/thermal.md) [P]
- IPC chart history: https://pcdandf.com/pcdesign/index.php/2009-archive-articles/5731-determining-current-carrying-capacity [S]; IPC-2152 test board: https://blog.mbedded.ninja/pdfs/JackOlson-HowTo2152.pdf [S]
- Thermal EMF: https://xdevs.com/doc/VPG/theremf.pdf [P]; https://docs.ampnuts.ru/eevblog.docs/Keithley/Ch3_LowLevMsHandbk.pdf [S]
- Reference stress: https://www.ti.com/document-viewer/LM4132/datasheet/layout [P]; https://www.ti.com/document-viewer/LM4140/datasheet/layout [S]
- Crystal curvature: https://www.raltron.com/webproducts/specs/CRYSTAL/R38.pdf [S]
- Emissivity: https://www.allpcb.com/allelectrohub/ir-temperature-sensors-for-non-contact-pcb-testing-a-practical-guide [S]
- Scripts: [tm_board_thermal_fv.py](../../../tools/research/physics/tm_board_thermal_fv.py), [tm_thermal_analytic.py](../../../tools/research/physics/tm_thermal_analytic.py)

See also: [hv-and-manufacturing-physics](hv-and-manufacturing-physics.md), [thermal-hv-mfg ideas](../../ideas/physics-first/thermal-hv-mfg.md), [../rules/thermal.md](../rules/thermal.md), [../rules/power/high-current.md](../rules/power/high-current.md), [power-copper](power-copper.md), [physics-critics-catalog](physics-critics-catalog.md)
