# Digest: high-speed, SI, EMC, stackup and interface rules

Scope: SI/EMC rules, stackup, diff pairs, interface packs, rule encoding, SI/EMI checkers. Not here: power/RF/analog/DFM -> [rules-power-rf-analog-dfm](rules-power-rf-analog-dfm.md); physics replacements -> [physics-first](physics-first.md). Ideas: [inventory](../ideas/inventory-rules-hs-emi.md).
Keys: return path, return via, rise time, t_r/6, via stub, crosstalk K, common mode, Class B, MREMC, stackup selection, diff-pair skew, uncoupled length, vendor spread, vendor profile, interface packs, connector zoning, TVS topology, myths, contested rules, rule strength tiers, checkers A–I

## Physics (the "why")
- Shared model (Ott, Hubing, Bogatin, Johnson, Hartley, Archambeault): HF return current flows in the adjacent plane under the trace; encode physics, not slogans. → [return current](../topics/rules/si-fundamentals.md#where-return-current-flows)
- Continuous reference copper under every fast net and each pair leg; merged antipads act as a slot. → [discontinuities](../topics/rules/si-fundamentals.md#discontinuities-splits-slots-voids-reference-changes)
- Reference changes: Ott's layer-change order; return via ≤200 mil, ~1.3 mm at PCIe Gen5 [I]; stitching caps (≤1 µF) only at unavoidable split crossings. → [SI rules](../topics/rules/si-fundamentals.md#si-design-rules)
- Rise time, not clock period: review at t_r/6, terminate at t_r/2 (contested); slow edges first; SerDes ≳3 Gb/s stubs < min(15 mil, 0.3/Gbps in). → [rise time](../topics/rules/si-fundamentals.md#rise-time-critical-length-termination-stubs)
- Crosstalk K = 1/(1+(D/H)²): reduce h first; no guard traces or ground fill by default. → [crosstalk](../topics/rules/si-fundamentals.md#crosstalk)
- EMI is mainly common-mode voltage between cables/chassis: ~1 mV can fail Class B; cable CM ≤5 µA (B) / 15 µA (A); MREMC makes "between connectors" computable. → [thresholds](../topics/rules/emc-placement.md#radiation-mechanisms-and-thresholds)
- One return-path EMF metric replaces about a dozen plane rules. → [fields](../topics/physics/fields-si-emi.md#3-the-one-metric-return-path-emf), [EMI budget](../topics/physics/fields-emi-budget.md#1-the-chain), [genealogy](../topics/physics/rule-genealogy-si-emi-rf.md)

## Stackup and differential pairs
- Choose the stackup before placement: Ott's five objectives, a candidate library, an 8-step scorer [I]. → [stackup](../topics/rules/stackup.md#stackup-selection-algorithm)
- Expert disagreements (common 6-layer; stripline for HS pairs) are warnings with a selector, not rejections. → [library](../topics/rules/stackup.md#candidate-library)
- Pairs are not self-returning; 20% skew (of t_r) gives 10% common mode: budget min(spec, 0.1·t_r) with running-skew compensation. → [pair rules](../topics/rules/diff-pairs.md#diff-pair-design-rules)
- Coupling tighter than ~0.5 mm buys no EMI benefit; rounded corners do not remove skew. → [pair physics](../topics/rules/diff-pairs.md#diff-pair-physics)
- TI keep-outs (30 mil, 50 mil to clocks) bind only HS interface pairs on TI parts; uncoupled ≤45 mil (corrected); jogs: a maximum spread. → [numeric](../topics/rules/diff-pairs.md#diff-pair-numeric-rules)

## Interfaces (vendor-keyed)
- Vendor values differ 5–25× (USB3 skew 2 mil vs 0.7 mm; DDR4 DQ↔DQS 2 ps vs 25 ps; Ethernet PHY↔magnetics <1 in vs ≥25 mm): vendor profiles are mandatory. → [vendor spread](../topics/rules/rule-pack-format.md#vendor-spread)
- Unknown vendor: tightest [P] value plus `info` (policy under review); windows intersect, empty asks. → [requirements](../topics/rules/rule-pack-format.md#rule-pack-requirements)
- Loss budgets over length limits; chain connector → ESD → (CMC) → AC cap → PHY is a hard intent. → [shared rules](../topics/rules/interfaces/common.md#chain-order-and-ac-caps)
- PCIe: TI SNLA426 loss budgets; 220 nF AC caps fit TI and Qualcomm for Gen3+. → [PCIe](../topics/rules/interfaces/pcie.md#pcie-rules-table)
- DDR: one `fromTo()` rule per SDRAM; byte-lane-only matching; TI matches to <20% of each limit. → [DDR](../topics/rules/interfaces/ddr.md#ddr-policy)
- Packs: [USB2](../topics/rules/interfaces/usb2.md#usb2-rules-table), [USB3/Type-C](../topics/rules/interfaces/usb3-usb4-typec.md#usb3-policy), [Ethernet](../topics/rules/interfaces/ethernet.md#ethernet-rules-table), [HDMI/DP](../topics/rules/interfaces/hdmi-dp.md#hdmi-vs-displayport-rules-table), [MIPI](../topics/rules/interfaces/mipi.md#qualcomm-d-phy-length-vs-rate-and-cable-loss) (cable-loss input), [SATA/UFS/SD](../topics/rules/interfaces/sata-ufs-sd.md#sata-rules), [CAN/RS-485](../topics/rules/interfaces/can-rs485.md#can-rules), [I2C/SPI](../topics/rules/interfaces/i2c-spi-qspi.md#i2c-rise-time-and-bus-capacitance-limits).
- Crystals: annulus from a vendor minimum (Espressif ≥2.0–2.7 mm) to 12 mm; score parasitic capacitance; can grounding and guard tie are vendor switches. → [crystals](../topics/rules/crystals-clocks.md#crystal-placement-and-scoring-rules)

## EMC placement
- Cabled connectors on one edge or corner; no HS circuitry between connectors; I/O devices ≤~2 cm from their connector, others ≥2 cm. → [zoning](../topics/rules/emc-placement.md#connector-zoning)
- 7-step placement order: 1–3 hard, 4–6 soft. → [order](../topics/rules/emc-placement.md#placement-priority-order)
- No primary mm TVS distance: connector → TVS → IC as comparative constraints, no via before the TVS, ESD corners ≤45°. → [TVS](../topics/rules/emc-placement.md#tvs-topology)
- HS pairs ≥90 mil from plane edges (TI scope); fast traces ≥2h from the board edge. → [edges](../topics/rules/emc-placement.md#edges)
- Stitching layout is contested: measure the largest unstitched region. → [stitching](../topics/rules/emc-placement.md#stitching)

## How rules are classified and encoded
- Myths (90° corners below ~2 Gb/s single-ended; bare 3W) become negative rules carrying their replacement. → [myths](../topics/rules/myths-and-contested.md#myths-and-context-dependent-rules)
- 20-H, guard traces, split grounds: context-dependent, never defaults; both variants plus a selector. → [contested](../topics/rules/myths-and-contested.md#contested-rules-requiring-an-explicit-selector)
- Tiers: hard fab, hard topology, hard in declared scope, soft-strong, soft-weak, context switch; blog-only mm become rank objectives. → [tiers](../topics/rules/rule-pack-format.md#rule-strength-tiers)
- Precedence interface 20 < vendor 30 < datasheet 40; [S] never overrides [P]; fab/safety minimums are floors after resolution. → [resolution](../topics/rules/rule-pack-format.md#resolution-policy)
- KiCad 10: ps delay, `fromTo()`, backdrill; master adds `return_path`, `stub_length`, net chains, via stitching. → [native](../topics/rules/checkers-si-emi.md#kicad-native-capability)
- Custom checkers A–I cover the rest; rank findings by consequence, not count. → [checkers](../topics/rules/checkers-si-emi.md#custom-checker-specifications)
- Reusable: kicad-happy, EMI Guardian (MIT), emcvisual (0BSD-style), RF-tools (GPL-3.0); `return_path` checker and EMC Auditor are reference only. → [open checkers](../topics/rules/checkers-si-emi.md#existing-open-source-checkers)
- No public tool closes generate → route → physics-check inside KiCad. → [policy](../topics/rules/checkers-si-emi.md#siemi-checker-policy)
