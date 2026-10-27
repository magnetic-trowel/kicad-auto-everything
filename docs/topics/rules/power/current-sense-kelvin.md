# Current-sense shunts and Kelvin connections

**TL;DR**
- **Use 4-wire Kelvin connections.** Sense traces are equal-length, equal-width, short, and terminate at the **centre of the inner pad edge** (onsemi). This closes the earlier tap-point gap.
- **Amplifier on the same side and near the shunt.** Route the pair tightly coupled and never parallel to switching nets.
- **Place filter R/C at the IC,** not at the shunt (BQ76952, AN-136, TPS922050).
- **Net ties force Kelvin routing** (TI SLVA959, which is tool-agnostic). In KiCad a net tie is a schematic symbol plus a footprint with `net_tie_pad_groups`, so it comes from the schematic.
- **Why it matters:** pad and solder IR drop is comparable to the shunt voltage. Poor layout causes 10–15%+ error.

## Key facts
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
- **Motor drivers** ([TI SLVA959B](https://www.ti.com/lit/pdf/slva959)) [P]:
  - Low-side shunt between the LS source and the star ground; high-side shunt near the star, with the first gain resistor nearest the shunt.
  - Tightly coupled differential pair; a net tie between device and shunt to enforce routing during placement.
  - Never parallel to switching signals; ~1 nF at the CSA pins.
  - Example: 20 A through 1 mΩ dissipates 400 mW for only a 20 mV signal.
  - See [motor-drivers.md](motor-drivers.md).
- **BMS** ([TI BQ76952 §18](https://www.ti.com/lit/ds/symlink/bq76952.pdf)) [P]:
  - "The quality of the Kelvin connections at the sense resistor is critical." TC ≤50 ppm; designed for 1 mΩ.
  - 100 Ω + 0.1 µF filter placed "as close as possible to the device, rather than close to the sense resistor", with parallel traces from the shunt.
  - See [chargers-bms.md](chargers-bms.md).
- **LED drivers:** CSP/CSN parallel and short, with R_FLT 100 Ω and optional 1 nF C_FLT at the IC ([led-drivers.md](led-drivers.md)).
- **Thermal:** copper in the sensed current path adds temperature sensitivity ([NextPCB](https://www.nextpcb.com/blog/current-sense-resistor-pcb-layout-kelvin-connection)) [V].

**Rules:**

| ID | Rule | Check | Sev |
|---|---|---|---|
| PWR-14 / AMS-09 / HC-06 | 4-wire Kelvin on all precision sense points (shunts, remote sense, reference returns); equal pair; tap inside the pad region | Sense nets as diff pair; length mismatch; tap point inside the pad; no shared copper with the power path between sense points | S1 |
| MOT-04 | Shunt to star ground; Kelvin pair through net ties; ~1 nF at the CSA | Net-tie presence; diff-pair rule; coupling scan | S1 |
| BMS-01 | Filter parts nearer the IC than the shunt | Distance comparison | S1 |
| LED-02 | CSP/CSN pair, filter at the IC | Diff-pair rule; coupling scan vs SW | S1 |

## Recommendations for our system
- **RSENSE role detector:** a low-ohm (≤100 mΩ) resistor in a power path whose ends go to CS±/SENSE/SRP/SRN/CSP/CSN pins.
- **Propose net ties** at the shunt pads as a schematic change (net-tie symbol + footprint), then update the PCB, so the router cannot share copper. A board-only footprint fails the referee's `--schematic-parity` check as `extra_footprint` ([drc-report-and-repair-loop.md](../../kicad/drc-report-and-repair-loop.md)).
- **Geometric checks:**
  - tap point within the inner half of the pad;
  - pair length mismatch;
  - parallel-run coupling against SW and gate nets;
  - comparative distance (filter closer to the IC than to the shunt).

## Conflicts and open questions
- **The shunt datasheet's land pattern overrides generic tap rules.**

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 1, § 11, § 13](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also: [motor-drivers.md](motor-drivers.md), [chargers-bms.md](chargers-bms.md), [../precision-sensing.md](../precision-sensing.md)
