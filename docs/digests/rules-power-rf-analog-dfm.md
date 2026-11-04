# Digest: power, PDN, RF, analog, isolation, thermal, DFM rules

Scope: survey conclusions on converters, PDN, RF, analog, isolation, thermal, DFM and power checkers. Not here: SI/EMC, stackup, interfaces -> [rules-hs-emi-interfaces](rules-hs-emi-interfaces.md); physics derivations of these rules -> [physics-first](physics-first.md). Ideas: [inventory](../ideas/inventory-rules-power.md).
Keys: hot loop, loop inductance nH, buck order, CIN distance, hard vs soft rule, context switch, C_boot, IPC-2221B B4, NOT FOUND values, SLVA959 via error, target impedance, mounting inductance, mixed-signal ground, TIA regimes, creepage lookup chain, fab floor, criticality map

## Hot loops and converters
- Every source ranks the switching hot loop first; topology fixes its membership. → [hot-loop rules](../topics/rules/power/hot-loops.md#hot-loop-rules-all-topologies), [membership](../topics/rules/power/hot-loops.md#hot-loop-membership-by-topology)
- Score loops in nH, not mm: real loops 2 mm² vertical <0.5 nH vs 20 mm² lateral >1 nH (SNVA803); AN-139 (187 vs 13 nH) gives only the plane-distance trend; no primary pass/fail loop area. → [loop thresholds](../topics/rules/power/hot-loops.md#loop-area-thresholds), [plane distance](../topics/rules/power/hot-loops.md#measured-loop-inductance-vs-plane-distance)
- Loop geometry physics: height × squares, via clusters. → [commutation loops](../topics/physics/pdn-and-commutation.md#1-commutation-loop-geometry)
- Buck order IC → CIN → L/SW → COUT/VOS → small-signal → single ground tie; MPS "<2 mm" is the only numeric primary CIN distance; no vendor gives a numeric SW-to-FB clearance. → [buck order](../topics/rules/power/buck.md#buck-order-and-cin), [feedback](../topics/rules/power/buck.md#buck-feedback), [boost](../topics/rules/power/boost.md#boost-rules)
- Classify power copper by waveform before sizing it. → [classification](../topics/physics/power-copper.md#1-node-and-branch-classification-the-decision-procedure)

## Translating datasheets into rules
- Topology facts are hard, distances soft: CIN on the IC layer (integrated converters; vias scored through the inductance estimate, so vertical loops stay legal), FB/VOS from the COUT pad, one AGND–PGND tie where "mandatory", shunt match via the named pin, antenna keep-out polygon. → [hard vs soft](../topics/rules/datasheet-to-constraints.md#hard-vs-soft-classification)
- Contested rules get a context switch, not a default: copper under inductors (Rohm vs TI), CIN/COUT ground, thermal-via tenting, "smallest cap closest", perimeter stitching, PMIC ground cuts, 20-H. → [why vendors disagree](../topics/rules/datasheet-to-constraints.md#why-vendors-disagree)
- Catalog numbers were mostly right but lost their conditions: records carry `source_scope`, `statement_strength`, `contested_by`; prefer rank orders and ratios to invented mm. → [record fields](../topics/rules/datasheet-to-constraints.md#rule-record-fields)
- Each rule of thumb's origin and physics replacement. → [genealogy](../topics/physics/rule-genealogy-power-analog-thermal.md#switching-converters-hot-loopsrulespowerhot-loopsmd-buckrulespowerbuckmd-flybackrulespowerflyback-offlinemd)

## Corrections to carry forward
- C_boot ≥10 × C_g and C_VDD ≥10 × C_boot: minimums, not "about 10×". → [gate drive](../topics/rules/power/gate-drive-bootstrap.md#gate-drive-checks-to-emit)
- IPC-2221B B4 above 500 V: 0.00305 mm/V (not 0.005). → [Table 6-1](../topics/rules/isolation-creepage.md#ipc-2221b-table-6-1)
- JLCPCB silk ≥1.0 mm text / 0.15 mm line; test pads 1.0 mm from parts; fiducial edge distance = SMEMA 7.62 mm + clearance on own-edge conveying, else the assembler's rail spec. → [DFM rules](../topics/rules/dfm-fab-limits.md#dfm-rules), [fiducials](../topics/rules/dfm-fab-limits.md#fiducials)
- NOT FOUND in primaries: u-blox ≤2 mm fence pitch, RF↔SMPS 20 mm, a 50–60% miter, 2 cm²/W; Espressif's 15 mm is enclosure clearance, not a PCB keep-out. → [RF rules](../topics/rules/rf.md#rf-rules), [LDO](../topics/rules/power/ldo.md#ldo-rules)
- Vendor errors: SLVA959's 5.73 °C/W per via (a plated barrel is ~150–261 °C/W); via-current tables differ 2.6×; AN-72 gives two spark-gap distances. → [SLVA959 errors](../topics/rules/power/motor-drivers.md#errors-in-slva959), [via ampacity](../topics/rules/power/high-current.md#via-ampacity), [AN-72](../topics/rules/power/flyback-offline.md#open-questions)

## Domain rules
- PDN: mounting inductance governs, not value; target impedance on the transient share only, flat profile, peaks ≤1.57 × Z_t; derate MLCCs, beads at ~20% of rating; no open-source PDN screener exists. → [PDN rules](../topics/rules/decoupling-pdn.md#decoupling-and-pdn-rules)
- RF: per-part module data is primary; match at the pin; only GND under RF on every layer except datasheet-mandated voids; λ_g/20 stitching is soft; arcs or 135° corners. → [RF rules](../topics/rules/rf.md#rf-rules)
- Mixed-signal: one partitioned plane chosen by ADC bits (isolated regions only at ≥14 bits); low-digital-current converters' AGND/DGND to analog ground at the package; guard high-Z nodes; minimise summing-node copper. → [grounding](../topics/rules/analog-mixed-signal.md#mixed-signal-grounding-rules)
- Precision: the dominant error picks the rules; the two photodiode-TIA regimes need opposite copper, so classify first. → [precision rules](../topics/rules/precision-sensing.md#precision-front-end-rules), [Kelvin](../topics/rules/power/current-sense-kelvin.md#kelvin-sensing-rules)
- Isolation: spacing is a lookup chain (voltage, pollution degree, material group, OVC, altitude, grade); IPC-2221B is functional only; slots count at ≥1.0 mm (PD2); human-confirmed classes. → [safety spacing](../topics/rules/isolation-creepage.md#safety-spacing-rules), [flyback](../topics/rules/power/flyback-offline.md#flyback-checks-to-emit)
- Circuit classes each get a detector, roles and constraints; datasheet ordered lists become `placement_priority`; net ties enforce Kelvin connections. → [motor](../topics/rules/power/motor-drivers.md#motor-driver-checks-to-emit), [LED](../topics/rules/power/led-drivers.md#led-driver-rules), [charger/BMS](../topics/rules/power/chargers-bms.md#charger-and-bms-checks-to-emit), [class-D](../topics/rules/power/class-d-audio.md#class-d-checks-to-emit)
- Thermal: R_θJA describes the JEDEC test board; ≥15.3 cm²/W board area, ~261 °C/W per 12 mil via, copper weight by dissipation, a screening estimator per placement. → [thermal rules](../topics/rules/thermal.md#thermal-rules), [fin physics](../topics/physics/thermal-physics.md#decompressing-the-ti-thermal-rules)
- DFM: fab and safety minimums are floors after resolution (effective_min = max(resolved, fab, safety)); a pack asking less is a conflict; also clamp each emitted rule; the router targets recommended values. → [resolution policy](../topics/rules/rule-pack-format.md#resolution-policy), [DFM rules](../topics/rules/dfm-fab-limits.md#dfm-rules)

## Checkers and method
- Place by constraint rigidity, template-first then global; route critical nets first and freeze them. → [methodology](../topics/rules/placement-methodology.md#placement-methodology-rules)
- The LLM extracts roles and classifies; code checks geometry and physics; a human confirms criticality map and safety classes. → [checker rules](../topics/rules/checkers-power.md#checker-design-rules)
- Build first: converter detector with hot-loop polygon, loop-inductance estimator, creepage engine, PDN/thermal screeners, KiCad-style marker reports; no open-source equivalent exists. → [checker rules](../topics/rules/checkers-power.md#checker-design-rules)
- The criticality map is the LLM's core contribution (Pease: knowing which circuits are critical is tacit). → [criticality map](../topics/rules/checkers-power.md#criticality-map)
