# Precision sensor front ends: thermocouple, bridge, photodiode TIA, electrometer

**TL;DR**
- **Each sensor class has a different dominant error, and the layout rules follow from it:**
  - thermocouple: parasitic junctions and gradients;
  - bridge: lead/trace resistance and parasitic thermocouples;
  - high-speed TIA: capacitance at IN−;
  - fA–pA TIA: leakage.
- **The two TIA regimes need opposite copper rules.** High-speed: remove the ground pour around IN−. Ultra-low current: add a driven guard on both sides. **Classify the regime first.**
- **Thermocouple:** the connector is an isothermal cold-junction block, the CJ sensor sits on it, and TC± routes are symmetric.
- **Bridge:** ratiometric reference plus 6-wire Kelvin sense; short, balanced traces; R_G at the amplifier pins.
- **The ground-noise budget comes from the ADC LSB** (Ott table), which also chooses the partition strategy.

## Key facts

**Thermocouple** ([TI SBAA274](https://www.ti.com/lit/pdf/sbaa274)) [P]:
- "Any connection between two different metals creates a thermocouple junction. Connections from the thermocouple to the ADC should be simple and symmetric." Errors matter when the board or device has a gradient.
- Both return leads at the same known temperature: a cold-junction block, often a connector with large metal mass. "It may be sufficient to maximize the copper fill around the junctions … layering … between top and bottom layers." An enclosure may be needed against air currents.
- CJ measured by diode, thermistor or RTD; its error passes directly into the result.
- Seebeck coefficients (µV/°C at 0 °C): J 50.37; K 39.48; T 38.74; E 58.70.

**Bridge** ([TI SBAA532A](https://www.ti.com/lit/an/sbaa532a/sbaa532a.pdf); [TIDUB00](https://www.ti.com/lit/pdf/tidub00)) [P]:
- 6-wire: V_SENSE± form a Kelvin connection that removes lead-resistance error and makes V_REF equal the voltage driving the bridge (ratiometric).
- Parasitic thermocouples give temperature-varying offset; ADC bias current through lead and filter R adds offset. AC excitation (polarity swap, subtract) cancels them.
- TIDUB00: bridge and common-mode resistor traces "as short and balanced as possible"; terminal block placed (bottom) for close connection of the input resistors; R_G as close to the amplifier pins as possible; solid plane; decoupling close.

**Photodiode TIA, high-speed** ([TI TIDU535](https://www.ti.com/lit/pdf/tidu535), 1 MHz) [P]:
- Parasitic capacitance at the inverting input can destabilise the circuit: "the ground pour of the PCB is removed in the areas around the inverting input of the op amp on both layers".
- C_F is necessary for stability.
- 49.9 Ω output resistor isolates cable capacitance, with a 50 Ω microstrip to the connector.

**Ultra-low current / electrometer** ([TI SBOA034](https://www.ti.com/lit/an/sboa034/sboa034.pdf)) [P]:
- Guarded input; "circuit must be well shielded".
- Resistors carry ~0.5 pF stray, which matters in the feedback network.
- Low-leakage, low-dielectric-absorption caps: NPO/C0G, polycarbonate, polystyrene, silver mica.
- fA TIA: guard the through-hole cathode pin on the bottom side too ([TI E2E LMP7721](https://e2e.ti.com/support/amplifiers-group/amplifiers/f/amplifiers-forum/1271048/lmp7721-transimpedance-amplifier---question-about-layout-guard-and-copper-pours)) [S].

**Williams AN47** [P]: 1 pF across a 1 kΩ feedback resistor caused severe peaking.

**Ott LSB budget** [P]: 12-bit / 1 V → 240 µV; 16-bit → 15 µV (full table in [analog-mixed-signal.md](analog-mixed-signal.md)).

**Rules** (RPA §15) [I]:

| ID | Rule | Numeric | Check | Sev |
|---|---|---|---|---|
| SEN-01 | TC connector is an isothermal block (pours both layers, stitched); CJ sensor on it; TC± symmetric (same layer, same vias) | Error ~40 µV/°C (K) per degree | CJ-sensor distance to the connector island; TC± length/via/layer symmetry | S1 |
| SEN-02 | Heat sources away from the TC connector/CJ block and input path | ≥15–20 mm from >0.5 W parts [I] | Thermal-distance check | S2 |
| SEN-03 | Bridge: ratiometric REF, 6-wire Kelvin, balanced input traces, R_G at the INA pins | Equal ± geometry | Pairwise length/geometry match; R_G distance | S1 |
| SEN-04 | TIA regime. **High-speed** (BW ≳100 kHz, R_F ≲1 MΩ): remove GND under/around IN− on all layers. **Ultra-low** (fA–pA, R_F ≳100 MΩ): driven guard at IN+ potential, both sides incl. TH pins, low-leakage parts | Thresholds are [I] | IN− copper area per layer, or guard-net presence | S1 |
| SEN-05 | R_F ∥ C_F directly across IN−/OUT; shortest IN− copper; photodiode next to IN− | 0.5–1 pF strays rival C_F | IN− total copper | S1 |
| SEN-06 | ADC resolution selects single-plane (≤12 bit) vs isolated regions (≥14 bit) | Ott LSB table | BOM-driven rule | S2 |

## Recommendations for our system
- **Detectors:**
  - Thermocouple: a TC connector footprint or nets named TC±, plus an NTC/RTD/temperature IC → CJ co-location + symmetric routing.
  - Bridge: excitation/sense/signal nets of a 4- or 6-wire connector → ratiometric REF + matched routing.
  - TIA: an op-amp with R_F ≥~100 kΩ and a photodiode on IN− → regime classification (SEN-04) before any copper rule.
- **BOM check:** low-leakage capacitor dielectrics in electrometer feedback.
- **Symmetry metrics** (length, via count, layer) for TC± and bridge pairs, plus a thermal-distance check fed by the [thermal estimator](thermal.md).

## Conflicts and open questions
- **The TIA regime thresholds are ours.** No source gives them.
- **Not read:** RTD 3/4-wire routing notes and ADI AN-43 (Williams, bridges).

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 15, § 19](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md)

See also: [analog-mixed-signal.md](analog-mixed-signal.md), [power/current-sense-kelvin.md](power/current-sense-kelvin.md), [thermal.md](thermal.md)
