# Battery chargers and BMS (monitors / protectors)

**TL;DR**
- **Switching chargers are buck converters with an explicit ordered layout list.** BQ25895: "Layout PCB according to this specific order is essential". Emit it as `placement_priority`.
- **SW copper on one layer only** ("do not use multiple layers in parallel"). This is a good default for every buck.
- **BMS pack shunt:** 4-wire Kelvin, with the RC filter **at the IC, not at the shunt**, and parallel traces from the shunt.
- **Cell-tap RC filters at the monitor IC;** cell traces in order without crossing; balance resistors spread for heat.
- **Spacing classes** scale with stack voltage (16S Li-ion ≈ 67 V). Use PCB spark gaps at the pack terminals.

## Key facts
- **TI BQ25895 §11.1** (SLUSC88C; [datasheet](https://www.ti.com/lit/ds/symlink/bq25895.pdf)) [P]. Minimise SW rise/fall times and the HF loop. Then, in order:
  1. Input cap as close as possible to PMID and GND, using the shortest copper or the plane.
  2. Inductor input terminal as close as possible to SW. Minimal copper area, but wide enough for the charge current. "Do not use multiple layers in parallel for this connection." Minimise parasitic C to other traces.
  3. Output cap near the inductor and IC, its ground tied to the IC ground by short copper or the plane.
  4. Route AGND separately from PGND; join them at the power pad (single point) or with a 0 Ω resistor.
  5. Make that single tie just beneath the IC. Use a ground pour, but keep it off the power pins.
  6. Decoupling caps next to the IC pins.
  7. EP soldered, with sufficient thermal vias.
  8. Via size and count sufficient for the current.

  Electrical: PMID ≥8.2 µF without OTG; 40 µF (≤2.4 A) or 60 µF (≤3.1 A) with OTG.
- **TI BQ76952 §18.1** (3–16S monitor/protector; [datasheet](https://www.ti.com/lit/ds/symlink/bq76952.pdf)) [P]:
  - "The quality of the Kelvin connections at the sense resistor is critical." TC ≤50 ppm; designed for 1 mΩ; paralleled resistors OK if Kelvin is preserved.
  - 100 Ω from each shunt terminal to SRP/SRN, 0.1 µF across SRP–SRN (optional 0.1 µF from each to ground).
  - "All filter components should be placed as close as possible to the device, rather than close to the sense resistor, and the traces from the sense resistor routed in parallel to the filter circuit." A ground plane around the filter helps.
  - REG18 decoupling at its pin, low inductance, to a ground plane tied to VSS.
  - I2C: Zener + series resistor for ESD.
  - Reference layout: 2-layer, 2.75 × 3.9 in; cells on the left edge, pack on the top edge; wide high-current paths; copper spark gaps (E prefix, no part fitted).
- **Cell filters** (TI E2E) [S]: typically 20 Ω series per cell input with 0.22 µF (1 µF also acceptable). R may rise to 100 Ω, but no further, or measurement errors appear.
- **TI SLUAA81** [S]: 20 Ω is the minimum input filter R for internal balancing; balance FET R_DS(on) is about 25 Ω; each balancing cell adds current into VC16, causing IR drop.

**Rules** (RPA §13) [I]:

| ID | Rule | Numeric | Check | Sev |
|---|---|---|---|---|
| CHG-01 | Follow the charger's ordered list exactly | As datasheet | Order-of-placement check; PWR-01 loop on {C_PMID, PMID, PGND} | S1 |
| CHG-02 | SW copper on one layer only | — | SW-net copper on >1 layer → flag | S2 |
| BMS-01 | Pack shunt Kelvin; SRP/SRN filter at the IC; parallel pair | 100 Ω + 0.1 µF (BQ76952) | Filter nearer the IC than the shunt; diff pair | S1 |
| BMS-02 | Cell RCs at the monitor; cell traces ordered, uncrossed; balance resistors spread away from the monitor and NTCs | 20–100 Ω / 0.1–1 µF (part-specific) | Filter-to-pin distances; thermal spread | S2 |
| BMS-03 | High-current path (pack±, FETs, shunt) as wide pours, off the monitor ground; monitor ground tied at the datasheet point | — | Shared-copper analysis vs monitor VSS | S1 |
| BMS-04 | Spacing between cell taps and pack terminals scales with stack V; spark gaps at the pack | 16S ≈ 67 V → IPC-2221B functional spacing | Net voltage classes from cell index | S1 |

## Recommendations for our system
- **Charger detector:** pins PMID/VBUS/SW/BAT/REGN/BTST/ILIM/TS → emit the ordered list + CHG-02.
- **BMS detector:** VC0…VCn, SRP/SRN, BAT, PACK, CHG/DSG gate pins.
  - Roles: cell-filter RCs, pack shunt, protection FETs.
  - Assign voltage classes from cell index × cell voltage, feeding [../isolation-creepage.md](../isolation-creepage.md).

## Conflicts and open questions
- **Not read:** daisy-chained BMS layout guidance (isoSPI, LTC681x, BQ79616) and linear or power-path charger layout guides.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 13, § 20](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md)

See also: [buck.md](buck.md), [current-sense-kelvin.md](current-sense-kelvin.md), [high-current.md](high-current.md)
