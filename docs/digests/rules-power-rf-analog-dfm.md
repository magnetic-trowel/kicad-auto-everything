# Digest: power, PDN, RF, analog, isolation, thermal, DFM rules

Executive statements. The detail, numbers and sources are in the linked topic docs, and every idea is listed in [the idea inventory](../ideas/inventory-rules-power.md).

## What matters most
- **The switching hot loop ranks first in every source.** Membership follows from the topology, and inductance can be measured: 2 mm² <0.5 nH vs 20 mm² >1 nH for real hot loops (TI SNVA803); 187 nH single-layer vs 13 nH over a plane 0.12 mm away for a 10 × 10 cm test loop at 27 MHz (AN-139). Score loops in nH, not millimetres. → [hot-loops](../topics/rules/power/hot-loops.md)
- **Buck order: IC → CIN → L/SW → COUT/VOS → small-signal → single ground tie.** MPS's <2 mm is the only numeric CIN distance found, and no vendor gives a numeric SW-to-FB clearance. → [buck](../topics/rules/power/buck.md), [boost](../topics/rules/power/boost.md), [buck-boost-sepic](../topics/rules/power/buck-boost-sepic.md)
- **Topology facts are hard constraints; distances are soft.** Hard: CIN on the IC layer for integrated converters (vias and plane coverage are scored by the inductance estimate, so vertical loops stay legal), FB sensed at the COUT pad, one AGND–PGND tie where "mandatory", shunt cap grounded through the named pin, antenna keep-out polygon. → [datasheet-to-constraints](../topics/rules/datasheet-to-constraints.md)
- **Some rules are genuinely contested and need an explicit selector, not a default.** Copper under inductors (Rohm vs TI), CIN/COUT ground separation, thermal-via tenting, "smallest cap closest", perimeter stitching, 20-H, PMIC ground cuts. → [datasheet-to-constraints](../topics/rules/datasheet-to-constraints.md)
- **Catalog numbers were mostly right but lost their conditions.** Rules need `source_scope`, `statement_strength` and `contested_by` fields. Prefer comparative constraints (rank orders, ratios) over invented millimetres. → [datasheet-to-constraints](../topics/rules/datasheet-to-constraints.md)

## Corrections to carry forward
- **Corrected values:** C_boot ≥10× C_g and C_VDD ≥10× C_boot (minimums). IPC-2221B B4 rate is 0.00305 mm/V above 500 V. JLCPCB silk ≥1.0 mm / 0.15 mm. Test pads 1.0 mm from parts. Fiducial edge distance = SMEMA 7.62 mm + clearance for boards conveyed on their own edges (panels follow the assembler's rail spec). → [gate-drive-bootstrap](../topics/rules/power/gate-drive-bootstrap.md), [isolation-creepage](../topics/rules/isolation-creepage.md), [dfm-fab-limits](../topics/rules/dfm-fab-limits.md)
- **Unsupported or misattributed:** u-blox ≤2 mm fence pitch, RF↔SMPS 20 mm, a 50–60% miter and 2 cm²/W are NOT FOUND in primary sources. Espressif's 15 mm is enclosure clearance, not a PCB keep-out. → [rf](../topics/rules/rf.md), [power/ldo](../topics/rules/power/ldo.md)
- **Vendor documents contain errors:** TI SLVA959's 5.73 °C/W per via (should be about 150–261), via-current tables that differ 2.6×, and AN-72's two spark-gap distances. → [motor-drivers](../topics/rules/power/motor-drivers.md), [high-current](../topics/rules/power/high-current.md)

## Domain statements
- **PDN:** mounting inductance governs, not value. Use target impedance with only the transient share of the budget, a flat profile and peaks ≤1.57× Z_t. Derate MLCCs; run beads at ≤20% of rating. No open-source PDN screener exists. → [decoupling-pdn](../topics/rules/decoupling-pdn.md)
- **RF:** per-part module data is primary. The match sits at the pin, only ground goes under RF on any layer (except voids the datasheet mandates), λ_g/20 stitching is a soft objective, and RF uses arcs or 135° (the 90°-corner myth covers single-ended nets below about 2 Gb/s only). → [rf](../topics/rules/rf.md)
- **Mixed-signal:** one partitioned ground plane, chosen by ADC resolution (isolated regions only at ≥14 bits). AGND/DGND of low-digital-current converters to analog ground at the package. Guard high-Z nodes; minimise summing nodes. → [analog-mixed-signal](../topics/rules/analog-mixed-signal.md); crystals in [crystals-clocks](../topics/rules/crystals-clocks.md)
- **Precision sensing:** the dominant error picks the rules. The two photodiode-amplifier regimes need opposite copper treatment, so classify first. → [precision-sensing](../topics/rules/precision-sensing.md), [current-sense-kelvin](../topics/rules/power/current-sense-kelvin.md)
- **Isolation:** spacing is a lookup chain over voltage, pollution degree, material group, overvoltage category, altitude and grade. IPC-2221B is functional only. Slots ≥1 mm at pollution degree 2. A human confirms the safety classes. → [isolation-creepage](../topics/rules/isolation-creepage.md), [flyback-offline](../topics/rules/power/flyback-offline.md)
- **Circuit classes** each get a rule pack with detector, roles, loops and constraints. Datasheet ordered lists become placement priorities, and net ties enforce Kelvin connections. → [motor-drivers](../topics/rules/power/motor-drivers.md), [led-drivers](../topics/rules/power/led-drivers.md), [chargers-bms](../topics/rules/power/chargers-bms.md), [class-d-audio](../topics/rules/power/class-d-audio.md), [high-current](../topics/rules/power/high-current.md)
- **Thermal:** R_θJA describes the test board. Use board area ≥15.3 cm² per W of total dissipation, ~261 °C/W per via at 1 mm pitch and copper weight by dissipation, with a screening estimator running per placement. → [thermal](../topics/rules/thermal.md)
- **DFM:** fab and safety minimums are floors applied after rule resolution (effective_min = max(resolved, fab, safety)), not precedence ranks; a pack asking for less raises a conflict. Board Setup carries them too, as KiCad clamps clearances to the board minimum. The router targets the recommended values. Most limits are native KiCad DRC. → [dfm-fab-limits](../topics/rules/dfm-fab-limits.md)

## Implications for the system
- **Method:** expert placement order and template-first-then-global placement, with critical nets routed first and frozen. → [placement-methodology](../topics/rules/placement-methodology.md)
- **Division of labour:** the LLM extracts roles and classifies; code checks geometry and physics; a human confirms the criticality map and safety classes. → [checkers-power](../topics/rules/checkers-power.md)
- **Checkers to build first:**
  - converter detector with hot-loop polygon;
  - loop-inductance estimator;
  - creepage engine;
  - PDN and thermal screeners;
  - KiCad-style marker reports for the LLM repair loop.

  No open-source equivalent exists. → [checkers-power](../topics/rules/checkers-power.md)
- **The criticality map is the LLM's core contribution** (Pease: knowing which circuits are critical is tacit expertise). → [checkers-power](../topics/rules/checkers-power.md)
