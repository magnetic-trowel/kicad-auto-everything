# Offline and isolated flyback layout rules

**TL;DR**
- **At least four critical loops,** each tight: primary, clamp, secondary, bias. **"No loop area should be placed inside another loop"** (PI AN-72).
- **The drain node is the dominant noise source.** Keep its copper minimal, and keep quiet traces away from the drain, the transformer "belly", switching winding ends and the rectifier.
- **Single-point ground on each side,** joined only at the defined star.
- **Feedback taps before the post-filter inductor;** the post filter sits at the output terminals.
- **Safety:** >8 mm primary-to-secondary (PI device guidance), spark gaps, and Y-cap routing. Spacing comes from the [creepage engine](../isolation-creepage.md).

## Key facts

**PI AN-72 "Recommendations for Circuit Board Layout"** (InnoSwitch3, Nov 2025; [PDF](https://www.power.com/sites/default/files/documents/an-72_innoswitch3_family_design_guide_20251107.pdf)) [P]:
- **Loops:**
  - Primary loop (input filter cap, transformer primary, IC D–S) "must be tight and small as possible".
  - Clamp (RCD, or a ~200 V Zener + diode): minimise the loop between the clamp parts, the transformer and the IC. Keep the clamp physically away from the PRIMARY BYPASS pin.
  - Secondary loop (N_S, C_OUT, SR FET) tight. Give the SR FET terminals heatsinking copper. Keep the SR FET source to IC GROUND distance short.
  - "No loop area should be placed inside another loop."
- **Grounds:**
  - Single-point ground from the input filter cap to the SOURCE-pin copper.
  - On the primary, bias-supply ground and SOURCE ground are separate traces joined at a single point.
  - On the secondary, star ground at the R_IS node, with separate traces for the GND pin, C_OUT and the feedback parts.
  - No signal trace shares a path with AC switching currents; star-connect at the capacitor pad.
- **Component placement:**
  - PRIMARY BYPASS, SECONDARY BYPASS and FEEDBACK caps directly adjacent to their pins.
  - R_LS, R_BP, R_FB (upper and lower) and R_IS as close as possible to the pins, with short traces.
  - Feedback (R_FB upper) and the VOUT pin connect **before** the post-filter inductor. The post-filter L/C sit as close as possible to the output terminals.
  - With an input π filter, the filter inductor goes between the **negative** terminals of the input caps.
- **Keep-outs:**
  - Keep quiet traces (Y-cap, feedback return) away from the drain, from "underneath transformer belly", from the switching side of any winding, and from the output rectifier.
  - Keep the drain trace's area and length minimal (RFI).
- **Safety:**
  - >8 mm between primary and secondary, especially under the InSOP package and the transformer.
  - No traces under the IC; no spark gaps near or across the IC.
  - Spark gaps from the secondary terminals to one AC input after the fuse, plus one across the CM choke.
  - A 0.4 mm mylar pad for a heat spreader that crosses the barrier (reinforced).

**Snubbers and clamps.**
- RCD clamp: HV diode, nF-range cap, hundreds-of-kΩ resistor. Optional damping of 100 Ω–1 kΩ in series with the cap ([Infineon AN-1195](https://www.infineon.com/dgdl/an-1195.pdf?fileId=5546d462533600a40153559b13df115a)) [P].
- Secondary rectifier ringing can be more destructive than the primary, and Schottkys are especially sensitive; a secondary RC snubber may be needed ([ADI flyback snubber](https://ez.analog.com/cfs-file/__key/telligent-evolution-components-attachments/00-330-01-00-00-06-34-74/FlybackSnubberDesign.pdf)) [S].
- Snubber parts go as close as possible to the switch node and transformer, with low-ESL SMD parts; avoid shared primary/secondary returns ([next.gr](https://www.next.gr/tutorials/switching-power-supplies/flyback-snubber-design-tutorial)) [V].
- TI "Under the Hood of Flyback SMPS Designs": minimise the loop area of fast di/dt paths [S].

**Rules** (RPA §10) [I]:

| ID | Rule | Auto-check | Sev |
|---|---|---|---|
| FLY-01 | Loops from the netlist: primary {C_bulk, T.pri, Q, R_sense}; clamp {T.pri, D_clamp, C/R or TVS}; secondary {T.sec, D/SR, C_out}; bias {T.aux, D_bias, C_bias} | Ordered-pad polygon area per loop | S1 |
| FLY-02 | Loops do not nest | Polygon containment test | S2 |
| FLY-03 | Minimal drain copper; no quiet nets under the belly, drain or switching pins | Rule area = transformer body + drain hull + 1–2 mm [I] | S2 |
| FLY-04 | FB tap before L_post; post filter at the connector | FB divider top on the net between C_out and L_post | S1 |
| FLY-05 | Exactly one quiet/power ground join per side | Graph check | S2 |
| FLY-06 | Primary–secondary separation | Creepage/clearance engine | S1 |

## Recommendations for our system
- **Flyback detector:** a transformer with a primary winding on the HV bulk-cap net and an IC/FET drain on the other end.
  - Classify windings as primary, secondary or bias.
  - Roles: clamp; Y-cap (pins on primary and secondary classes); spark-gap footprints; post-filter L (series L after C_OUT, before the connector).
- **Emit FLY-01…06 plus ISO-01…07** from [../isolation-creepage.md](../isolation-creepage.md).
- **Spark gaps** are copper features, not parts. Check that the footprint is present and the gap is measured.

## Conflicts and open questions
- **AN-72 spark-gap distance** is internally inconsistent: 6.4 mm (5.5 mm acceptable) in the layout section vs "at least 5.4 mm" in the ESD section. Store both and use the device datasheet.
- **Only PI guidance was read.** TI UCC28740 and ST VIPer guides were not.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 1, § 9, § 10, § 20](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also: [../isolation-creepage.md](../isolation-creepage.md), [hot-loops.md](hot-loops.md), [../checkers-power.md](../checkers-power.md)
