# Current-sense shunts and Kelvin connections

Scope: canonical home for shunt/Kelvin sensing rules used by every power doc: 4-wire Kelvin, tap point, amplifier placement, filter at the IC, net ties, checks. Not here: precision analog sensing -> [../precision-sensing.md](../precision-sensing.md).
Keys: current sense, shunt, Kelvin, 4-wire, tap point, RSENSE, net tie, net_tie_pad_groups, CSA, SENSE±, DCR sensing, DN05117, N1702, copper TCR 3900 ppm, PWR-14, AMS-09, HC-06, MOT-04

## Kelvin sensing rules
1. 4-wire Kelvin: sense traces equal-length, equal-width, short, terminating at the **centre of the inner pad edge** (onsemi). Pad and solder IR drop is comparable to the shunt voltage; poor layout → 10–15%+ error.
2. Amplifier on the same side, near the shunt; pair tightly coupled, never parallel to switching nets.
3. Filter R/C at the IC, not at the shunt (BQ76952, AN-136, TPS922050).
4. Net ties force Kelvin routing (TI SLVA959, tool-agnostic). In KiCad a net tie = schematic symbol + footprint with `net_tie_pad_groups`: propose it as a schematic change, then update the PCB. A board-only footprint fails the referee's `--schematic-parity` check as `extra_footprint` ([drc-report-and-repair-loop.md](../../kicad/drc-report-and-repair-loop.md)).
5. RSENSE role detector: low-ohm (≤100 mΩ) resistor in a power path whose ends go to CS±/SENSE/SRP/SRN/CSP/CSN pins.
6. Geometric checks: tap within the inner half of the pad; pair length mismatch; parallel-run coupling vs SW and gate nets; filter closer to the IC than to the shunt.
7. The shunt datasheet's land pattern overrides generic tap rules.

## Kelvin evidence by source
- **onsemi DN05117** ([PDF](https://www.onsemi.com/download/design-notes/pdf/dn05117-d.pdf)) [P], VERIFIED:
  - Traces "equal length, equal dimension and as short as possible".
  - Amplifier and shunt on the "same side of the PCB".
  - Prefer "four terminal (also known as Kelvin) shunts".
  - Traces "terminate at the center of the inside of the pad relative to where the shunt resistor connects".
  - Poor layout causes "10% to 15% or more" error.
- **Bourns N1702** ([PDF](https://www.bourns.com/docs/technical-documents/technical-library/current-sense-pulse-power-high-power-resistors/application-notes/bourns_n1702_current_sense_accurate_measurement_appnote.pdf)) [P]:
  - Prefer 4-terminal parts. 2-terminal parts can use PCB-trace Kelvin connections but are less precise at high current.
  - For very low-ohm 2-terminal parts, R_lead + R_lead ≫ R_shunt.
  - Copper TCR is 3900 ppm/°C, against <50 ppm/°C for the element.
- **AN-139** [P]: keep the SENSE± gap minimal and run the pair on the far side of a shield plane.
- **AN-136** [P from mirror]:
  - Signals are typically <100 mV; route SENSE± in parallel at minimum spacing, with filter R/C as close to the IC as possible.
  - DCR sensing: R near the inductor, C near the IC.
  - A sense-return via must not contact an internal VOUT+ layer.
- Per-application specifics: motor drivers (shunt to star ground, net tie, ~1 nF at CSA; 20 A × 1 mΩ = 400 mW for 20 mV) -> [motor-drivers.md](motor-drivers.md); BMS (BQ76952 100 Ω + 0.1 µF at the IC, TC ≤50 ppm, 1 mΩ) -> [chargers-bms.md](chargers-bms.md); LED CSP/CSN (R_FLT 100 Ω, 1 nF) -> [led-drivers.md](led-drivers.md).
- **Thermal:** copper in the sensed current path adds temperature sensitivity ([NextPCB](https://www.nextpcb.com/blog/current-sense-resistor-pcb-layout-kelvin-connection)) [V].

## Kelvin rule IDs

| ID | Rule | Check | Sev |
|---|---|---|---|
| PWR-14 / AMS-09 / HC-06 | 4-wire Kelvin on all precision sense points (shunts, remote sense, reference returns); equal pair; tap inside the pad region | Sense nets as diff pair; length mismatch; tap point inside the pad; no shared copper with the power path between sense points | S1 |
| MOT-04 | Shunt to star ground; Kelvin pair through net ties; ~1 nF at the CSA | Net-tie presence; diff-pair rule; coupling scan | S1 |
| BMS-01 | Filter parts nearer the IC than the shunt | Distance comparison | S1 |
| LED-02 | CSP/CSN pair, filter at the IC | Diff-pair rule; coupling scan vs SW | S1 |

## Sources
- [rules_power_rf_analog_dfm.md § 1, § 11, § 13](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also: [motor-drivers.md](motor-drivers.md), [chargers-bms.md](chargers-bms.md), [../precision-sensing.md](../precision-sensing.md)
