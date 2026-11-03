# LDO layout rules

Scope: LDO cap placement, output routing, dissipation and copper. Not here: copper-area thermal rules -> [../thermal.md](../thermal.md); decoupling -> [../decoupling-pdn.md](../decoupling-pdn.md).
Keys: LDO, linear regulator, dropout, LDOIN, CIN, COUT, P = (V_IN − V_OUT)·I, 2 cm²/W, SNVA419, AN-PM-179, PWR-16

## LDO rules
No switching loop: CIN for load transients, COUT for stability; thermal dominates.

| Rule | Value / detail | Source |
|---|---|---|
| CIN | At LDOIN/PGND: "The LDO input capacitor should be placed as close as possible to the LDOIN and PGND pins. Trace impedances … minimized to reduce drop-out" (trace impedance adds to dropout and load regulation). Copper-plugged vias for lowest via impedance and best thermal | Renesas DA9080 AN-PM-179 ([PDF](https://www.renesas.com/en/document/apn/da9080-pcb-layout-recommendations)) [P] |
| Output routing | Through the output caps first, only then change layers or run to remote loads | Renesas, MPS [P] |
| Dissipation | `P = (V_IN − V_OUT) × I_OUT`; package + PCB copper must carry it | [PCBWay](https://www.pcbway.com/blog/PCB_Design_Layout/LDO_Power_PCB_Layout_Design_Guidelines_From_Basics_to_Best_Practices_8f3387c6.html) [V] |
| "Output caps within ~2 mm" | CORRECTED: MPS AN065's <2 mm applies to the **input** cap and VCC cap ([AN065](https://media.monolithicpower.com/document/PCB_Layout_Design_Guidelines_for_NB67xSeries.pdf)) | VR |
| "~2 cm² per W below 85 °C" | NOT FOUND in any primary source (PCBWay/Aivon blogs only) [V] | VR |
| Primary thermal rule | SNVA419 board area per W of total dissipation (board-size rule, not per-part) and EP vias at 1 mm pitch -> [thermal](../thermal.md#ti-snva419c-rules) | [TI SNVA419](https://www.ti.com/lit/pdf/snva419) [P] |
| PWR-16 (RPA §1) | CIN/COUT at pins, output through COUT before branching, copper sized for P; S2 | [I] |

## LDO checks
- Role detector: IC with IN/OUT/GND(/EN/FB), no SW pin; CIN/COUT by net.
- Pad distance CIN to LDOIN/PGND; topology check: output trace passes the COUT pad before any branch or via.
- Feed (V_IN − V_OUT)·I_max into the per-part thermal screener and the board-level SNVA419 Rule 1 check ([../thermal.md](../thermal.md)).

## Open questions
- No primary copper-area-vs-θ_JA curves for specific LDO packages extracted.

## Sources
- [rules_power_rf_analog_dfm.md § 1](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
