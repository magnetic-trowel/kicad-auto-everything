# Boost converter layout rules

Scope: boost-specific hot loop, cap ranking, VIN copper, AGND tie, detector. Not here: shared hot-loop rules -> [hot-loops.md](hot-loops.md); FB, SW, snubber rules -> [buck.md](buck.md).
Keys: boost, COUT_HF, output cap hot loop, rectifier, sync FET, SLVA773, SNVA731, PWR-09, Power-Ground

## Boost rules
| Rule | Value / detail | Source |
|---|---|---|
| Hot loop | LS switch (SW→PGND) → rectifier/HS (SW→VOUT) → COUT_HF → PGND; the **output** cap is critical, not the input cap. "In a boost converter, the most critical PCB feature is the loop formed by the output capacitor, diode and the regulator ground." | [TI SNVA731](https://www.ti.com/lit/an/snva731/snva731.pdf) [P, VERIFIED] |
| C_HF side | Output side, close to MOSFET and diode | AN-136 [P] |
| COUT placement | Close to IC, short wide traces; small-package cap next to IC, bulk farther away; COUT_HF ground returns to IC PGND by the shortest path and is the closest cap to PGND | [TI SLVA773](https://www.ti.com/lit/an/slva773/slva773.pdf) ("Five Steps to a Good PCB Layout of the Boost Converter") [P] |
| Vias | "One via per amp of current if the via is required." | SLVA773 |
| Power-Ground | CIN ground close to PGND; CIN, COUT and IC grounds "form a Power-Ground" | SLVA773 |
| VIN copper | Quiet: large VIN area acceptable; do not flag a large VIN pour as EMI risk | SLVA773 |
| FB | "Any trace of a sensitive node, such as FB, should be far away from the SW node"; not parallel to SW; no numeric FB–SW clearance in any vendor document | SLVA773 |
| AGND | "connected to the Power-Ground of the IC through a single point … close to the PGND pin" | SLVA773 |
| Loop area | "under 1 cm² if possible" only on a calculator page ([Firgelli](https://www.firgelliauto.com/blogs/engineering-calculators/boost-converter-calculator)) [V]; use [hot-loops.md](hot-loops.md#loop-area-thresholds) tiers | — |
| PWR-09 (RPA §1) | COUT_HF tight to rectifier and PGND; hot-loop area {LS FET, D, COUT_HF}; S1; also flyback secondaries | [I] |

## Boost detector and constraints
- Topology: inductor between input rail and SW + diode or sync FET from SW to output → boost. COUT_HF = smallest-package cap on VOUT/PGND.
- Hot-loop polygon {SW pin / LS FET, rectifier, COUT_HF, PGND}: COUT_HF on the IC layer hard (integrated converters); vias/plane scored by the loop-inductance estimate ([hot-loops.md](hot-loops.md)); soft area score.
- Boost LED drivers use the SW–D–COUT loop ([led-drivers.md](led-drivers.md)).

## Open questions
- SEPIC/Ćuk loop membership is inference only ([buck-boost-sepic.md](buck-boost-sepic.md)).

## Sources
- [rules_power_rf_analog_dfm.md § 1](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md); [interface_rule_packs.md § 8](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
