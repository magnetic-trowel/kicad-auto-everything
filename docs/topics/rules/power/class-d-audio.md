# Class-D amplifiers and low-frequency audio grounding

**TL;DR**
- **Class-D stages publish quantified loop-inductance budgets.** TI TAS2xxx targets 750–1150 pH total (pin-to-pin + cap ESL) per supply loop, with the smallest cap within 1 mm of the pin. This makes "close" measurable.
- **Switching outputs never run adjacent-layer to other signals** without a ground layer between.
- **Output EMC filter and snubbers at the IC;** the speaker connector lands on the filter-cap pads. Inputs go on the quiet side with ground floods.
- **Below ~100 kHz,** return currents don't hug the trace, so audio and precision DC need explicit return-path planning and a star at the power entry.

## Key facts
- **TI SLAA896** ("PCB Layout Guidelines for TAS2xxx Series Class-D Boosted Audio Amplifier", [PDF](https://www.ti.com/lit/pdf/slaa896)) [P]:
  - 4–6 layers with epoxy-filled vias is ideal.
  - Short all ground pins together at the balls on top, stitched to a solid L2 ground with multiple vias; a dedicated ground layer is strongly recommended.
  - "The smallest decoupling cap is placed less than 1 mm of distance from the device pin and any further caps are placed next to it"; multiple vias at the cap pads.
  - Class-D output, SW node and Vsense never on an adjacent layer next to any other signal without ground shielding between.
  - Boost SW trace carries 5 A (device-dependent).
  - Vsense taps as close to the speaker terminals as possible, 6 mil, differential.
  - VBST strapped to PVDD right under the device on top (avoids IR droop and via inductance).
  - AVDD/VDD/IOVDD star-connected from the PMIC with 20–30 mil traces; charge-pump cap starred at the PVDD pin, not on the PVDD plane.
  - Table 2, optimum loop parasitics (pin-to-pin + cap ESL = total):

    | Loop | Pin-to-pin | Cap ESL | Total |
    |---|---|---|---|
    | DREG–GND | 650 pH | 500 pH | 1150 pH |
    | GREG–PVDD | 300 | 500 | 800 |
    | VBAT–GND | 650 | 500 | 1150 |
    | VBST–BGND | 250 | 500 | 750 |
    | VDD–GND | 350 | 500 | 850 |

- **TI TPA3110D2 PCB layout/EMC slides** ([PDF](https://e2e.ti.com/cfs-file/__key/telligent-evolution-components-attachments/00-06-00-00-00-05-21-80/PCBlyt_2D00_home_2D00_ent_2D00_audio_2B00_EMC_2B00_T_2D00_100818.pdf)) [P]:
  - IC at the centre of the ground plane; PowerPAD on thermal vias 0.33 mm on 1.0 mm centres.
  - HF decoupling within 1 mm of the IC, bulk next to them, grounded through multiple vias.
  - EMC snubbers and filters very near the IC.
  - Output terminals connect to the filter-cap pads directly or through broad copper (minimal unfiltered loops).
  - Inputs on the quiet side, shielded with top and bottom ground floods.
  - Analog control caps (GVDD, PLIMIT, AVCC) to the plane with multiple vias; AGND to the PowerPAD.
- **Low-frequency grounding** (Altium, Z. Peterson; [article](https://resources.altium.com/p/pcb-ground-plane-best-practices-your-multilayer-stackup)) [P]: default to a uniform plane and do not split without an isolation or safety reason. Corner case: audio and precision analog below ~100 kHz, where "return currents … do not follow closely to the trace". Engineered return paths and a power-entry star may be preferred.
- [TI SLYT182](https://www.ti.com/lit/an/slyt182/slyt182.pdf) [S]: continuous plane; power-section decoupling terminated near the ground pins.
- [EE Times](https://www.eetimes.com/circuit-board-layout-guidelines-for-class-d-amplifiers/) [S]: small output-filter loop; speaker connector close to the filter; filter grounds stitched.

**Rules** (RPA §16) [I]:

| ID | Rule | Check | Sev |
|---|---|---|---|
| AUD-01 | Decoupling loop-L budget per supply pin; smallest cap ≤1 mm (TAS2xxx, SLAA896) | Loop-inductance estimator vs budget (reusable for any IC that publishes one) | S2 |
| AUD-02 | OUT±, SW, BST never adjacent-layer to other signals without GND between | Layer-overlap scan, L±1 | S2 |
| AUD-03 | Output filter at the IC; connector at the cap pads; snubbers at the IC | Distances IC → filter caps, connector → cap pads | S2 |
| AUD-04 | Inputs on the quiet side, with floods; AGND to the EP centre | Region partition distance | S2 |
| AUD-05 | <100 kHz audio: plan returns; star the power entry; avoid ground loops through connectors/chassis | Flag shared ground copper between high-current returns (amp, LED, motor) and audio input references | S2 |

## Recommendations for our system
- **Class-D detector:** pins OUT±/SW/BST/PVDD/VBST/Vsense → AUD-01…03.
- **Use the SLAA896 pH budgets as calibration targets** for the [loop-inductance estimator](../checkers-power.md).

## Conflicts and open questions
- **Not researched:** the "pin 1 problem", cable-shield-to-chassis practice (Muncy, Rane) and analog audio grounding from primary sources.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 14, § 16](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md)

See also: [../decoupling-pdn.md](../decoupling-pdn.md), [../analog-mixed-signal.md](../analog-mixed-signal.md), [../checkers-power.md](../checkers-power.md)
