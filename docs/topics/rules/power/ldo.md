# LDO layout rules

**TL;DR**
- **There is no switching loop.** CIN is there for load transients and COUT for stability. Thermal dominates.
- **CIN goes at LDOIN/PGND,** because trace impedance adds to dropout and load regulation.
- **Route the output through COUT** before branching or changing layers.
- **Size copper from P = (V_IN − V_OUT)·I** with the [thermal estimator](../thermal.md). The common "2 cm²/W" figure has no primary source.

## Key facts
- **Renesas DA9080 AN-PM-179** ([PDF](https://www.renesas.com/en/document/apn/da9080-pcb-layout-recommendations)) [P]: "The LDO input capacitor should be placed as close as possible to the LDOIN and PGND pins. Trace impedances … minimized to reduce drop-out". It also recommends copper-plugged vias for the lowest via impedance and best thermal performance.
- **Routing:** route the output through the output caps first, and only then change layers or run to remote loads (Renesas, MPS) [P].
- **Dissipation:** P = (V_IN − V_OUT) × I_OUT; the package plus PCB copper must carry it ([PCBWay](https://www.pcbway.com/blog/PCB_Design_Layout/LDO_Power_PCB_Layout_Design_Guidelines_From_Basics_to_Best_Practices_8f3387c6.html)) [V].
- **VR corrections:**
  - The "output caps within ~2 mm" attribution is CORRECTED. MPS AN065's <2 mm applies to the **input** cap and the VCC cap ([AN065](https://media.monolithicpower.com/document/PCB_Layout_Design_Guidelines_for_NB67xSeries.pdf)).
  - "About 2 cm² per W to stay below 85 °C" is NOT FOUND in any primary source (PCBWay/Aivon blogs only) [V].
- **Primary thermal rules instead** ([TI SNVA419](https://www.ti.com/lit/pdf/snva419)) [P]: ≥15.3 cm²/W of two-sided copper for a 40 °C rise in still air; EP vias at 1 mm pitch.
- **Rule PWR-16** (RPA §1): CIN/COUT at the pins, output through COUT before branching, copper sized for P. Severity S2.

## Recommendations for our system
- **Role detector:** an LDO is an IC with IN/OUT/GND(/EN/FB) and no SW pin. Assign CIN/COUT by net.
- **Pad-distance checks:** CIN to LDOIN/PGND; output trace must pass through the COUT pad before any branch or via (topology check).
- **Feed (V_IN − V_OUT)·I_max into the thermal screener**, and flag when connected copper is below the SNVA419 requirement.

## Conflicts and open questions
- **No primary copper-area-vs-θ_JA curves** for specific LDO packages were extracted.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 1](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also: [../thermal.md](../thermal.md), [buck.md](buck.md), [../decoupling-pdn.md](../decoupling-pdn.md)
