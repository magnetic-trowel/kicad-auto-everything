# Inverting buck-boost, 4-switch buck-boost, SEPIC and Ćuk

Scope: hot-loop membership and constraints for these topologies. Not here: shared hot-loop rules -> [hot-loops.md](hot-loops.md); CIN-first, SW, FB, grounds -> [buck.md](buck.md), [boost.md](boost.md).
Keys: inverting buck-boost, 4-switch buck-boost, SEPIC, Ćuk, Cuk, coupling cap, half-bridge, INTVCC loop, loop_area

## Buck-boost family hot loops
| Topology | Hot loop members | Continuous (not hot) | Placement / constraint | Evidence |
|---|---|---|---|---|
| Inverting buck-boost | CIN, switch, diode/sync FET, COUT in one series loop | L | CIN and COUT grounds side by side at the IC (proximity constraint); one `loop_area` | [I] circuit analysis (RPA §1) |
| 4-switch buck-boost | Input half-bridge + CIN; output half-bridge + COUT | L | One HF cap right at each half-bridge's FETs; two `loop_area` | [I] |
| SEPIC / Ćuk | Switch → coupling cap → rectifier → COUT → GND → switch | L1, L2, CIN | Coupling cap inside the tight loop; soft `loop_area` flagged "unverified topology inference" until a datasheet confirms | [I], unconfirmed |

- AN-139 (Kueck, buck-boost example; [mirror](https://theengineer.markallengroup.com/production/content/uploads/2015/01/an139f.pdf)) [P]: input-cap hot loop RF energy >20 dB above the INTVCC decoupling loop; INTVCC/driver loop is second priority with a solid next-layer plane.
- Classifier hints (RPA §20) [I]: L from SW to GND with negative output → inverting buck-boost; two SW nodes with one L between → 4-switch buck-boost.

## Open questions
- No primary layout note for SEPIC/Ćuk or 4-switch buck-boost read: pull from the controller datasheet's Layout Guidelines ([../datasheet-to-constraints.md](../datasheet-to-constraints.md)).

## Sources
- [rules_power_rf_analog_dfm.md § 1, § 20](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md)
