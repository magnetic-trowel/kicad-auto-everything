# Digest: high-speed, SI, EMC, stackup and interface rules

This digest summarises `rules_highspeed_emi.md`, `interface_rule_packs.md` and the high-speed/EMC parts of `verification_rules.md`, whose corrections win. Detail lives in the linked topic docs; all ideas are in [inventory-rules-hs-emi.md](../ideas/inventory-rules-hs-emi.md).

## Physics (the "why")
- **One shared model** (Ott, Hubing, Bogatin, Johnson, Hartley, Archambeault): high-frequency return current flows in the adjacent plane, directly under the trace; EMI comes mainly from common-mode voltage between cables or chassis, and from imbalance or skew. Encode physics, not slogans. See [si-fundamentals](../topics/rules/si-fundamentals.md) and [emc-placement](../topics/rules/emc-placement.md).
- **Return-path rules** ([si-fundamentals](../topics/rules/si-fundamentals.md)):
  - continuous reference copper under every fast net and each leg of a pair;
  - Ott's layer-change order;
  - a return via within ≤200 mil, scaled with data rate (about 1.3 mm at PCIe Gen5);
  - stitching caps (≤1 µF) only at unavoidable split crossings;
  - merged antipads act as slots.
- **Timing is set by rise time, not clock period** ([si-fundamentals](../topics/rules/si-fundamentals.md)):
  - review at t_r/6, terminate at t_r/2 (contested threshold); slow edges first;
  - on SerDes ≳3 Gb/s, keep via stubs below min(15 mil, 0.3/Gbps in);
  - crosstalk follows K = 1/(1+(D/H)²), so reduce h first.
- **EMC thresholds** ([emc-placement](../topics/rules/emc-placement.md)): about 1 mV between antenna parts can fail Class B; cable common-mode limits are 5 µA (Class B) and 15 µA (Class A); LearnEMC's MREMC algorithm makes "no high-speed circuitry between connectors" computable.

## Stackup and differential pairs
- **Stackup** ([stackup](../topics/rules/stackup.md)): choose it before placement with Ott's five objectives, a candidate library and an 8-step scorer. Expert disagreements (Ott vs Hartley on the common 6-layer; TI vs Ott on stripline) are warnings with a selector, not rejections.
- **Differential pairs** ([diff-pairs](../topics/rules/diff-pairs.md)):
  - pairs are not self-returning;
  - 20% skew gives 10% common mode: budget min(spec, 0.1·t_r), with running-skew compensation;
  - coupling tighter than 0.5 mm buys no extra EMI benefit;
  - TI's keep-outs (30 mil to other signals, 50 mil to clocks) apply to high-speed interface pairs only;
  - uncoupled length ≤45 mil (corrected); jog "amplitude" becomes a maximum spread.

## Interfaces (vendor-keyed)
- **Vendor values differ 5–25×** (USB3 skew 2 mil vs 0.7 mm; DDR4 DQ↔DQS 2 ps vs 25 ps; Ethernet PHY↔magnetics ≥25 mm vs <25 mm), so vendor profiles are mandatory. Unknown vendor: currently the tightest primary value (policy under review); two-sided windows intersect, and an empty intersection asks. See [rule-pack-format](../topics/rules/rule-pack-format.md).
- **Per-interface packs** (loss budgets instead of length limits where possible):
  - [USB 2.0](../topics/rules/interfaces/usb2.md)
  - [USB3/USB4/Type-C](../topics/rules/interfaces/usb3-usb4-typec.md): connector → ESD → CMC → AC cap → PHY
  - [PCIe](../topics/rules/interfaces/pcie.md): TI loss budgets; 220 nF AC caps for Gen3+
  - [DDR](../topics/rules/interfaces/ddr.md): one `fromTo` rule per SDRAM; byte-only matching; 20% derating
  - [Ethernet](../topics/rules/interfaces/ethernet.md), [HDMI/DP](../topics/rules/interfaces/hdmi-dp.md), [MIPI](../topics/rules/interfaces/mipi.md) (cable-loss input), [SATA/UFS/SD](../topics/rules/interfaces/sata-ufs-sd.md), [CAN/RS-485](../topics/rules/interfaces/can-rs485.md), [I2C/SPI/QSPI](../topics/rules/interfaces/i2c-spi-qspi.md)
- **Crystals** ([crystals-clocks](../topics/rules/crystals-clocks.md)): an annulus from a vendor minimum (Espressif ≥2.0–2.7 mm) to ≤12 mm; score parasitic capacitance. Metal-can grounding, copper under the crystal and the guard tie are vendor switches.
- **Buck regulators and fab limits** are the power cluster's: [power/buck](../topics/rules/power/buck.md), [dfm-fab-limits](../topics/rules/dfm-fab-limits.md).

## EMC placement
- **Placement** ([emc-placement](../topics/rules/emc-placement.md)): cabled connectors on one edge or corner; no high-speed circuitry between connectors; I/O devices within about 2 cm of their connector, other parts at least 2 cm away; a 7-step placement order (1–3 hard, 4–6 soft).
- **Protection and edges** ([emc-placement](../topics/rules/emc-placement.md)):
  - TI gives no millimetre TVS distance, so encode connector → TVS → IC as comparative constraints: no via or stub before the TVS, a GND via at its pad, ESD-path corners ≤45°.
  - High-speed differential pairs ≥90 mil from the plane edge; fast traces ≥2h from the board edge.
  - Stitching (perimeter vs distributed) is contested, so measure the largest unstitched region.

## How rules are classified and encoded
- **Myths and contested rules** ([myths-and-contested](../topics/rules/myths-and-contested.md)): myths (90° corners on single-ended nets below about 2 Gb/s; a generic 3W) become negative rules that carry their physics replacement. 20-H, guard traces and split grounds are contested or context-dependent: never defaults; both variants plus a selector.
- **Rule tiers** ([rule-pack-format](../topics/rules/rule-pack-format.md)): hard fab limits; hard topology; hard within a declared scope; soft-strong; soft-weak; context switch. Blog-only millimetre values become rank objectives. Records carry `source_scope`, `statement_strength` and `contested_by`.
- **Rule packs** ([rule-pack-format](../topics/rules/rule-pack-format.md)): YAML with design-intent precedence interface 20 < vendor 30 < datasheet 40, `by_vendor` values, recorded conflicts, and [S] never overriding [P]. Fab and safety minimums are floors applied after resolution, not ranks.
- **KiCad native** ([checkers-si-emi](../topics/rules/checkers-si-emi.md)): KiCad 10 has ps delay, `fromTo` and backdrill; master adds `return_path`, `stub_length`, net chains and via stitching.
- **Custom checkers A–I** cover the rest: reference map, return continuity, reference change, via stubs, connector placement, crosstalk, stitching, protection topology and loop ranking ([checkers-si-emi](../topics/rules/checkers-si-emi.md)).
- **Reusable checkers** under GPL-3.0-or-later: kicad-happy and EMI Guardian (MIT), emcvisual (0BSD-style), RF-tools (GPL-3.0). The `return_path` checker and EMC Auditor are reference only ([checkers-si-emi](../topics/rules/checkers-si-emi.md)).
- **The gap.** No public tool closes the loop (generate constraints → route → physics-check) inside KiCad; existing tools only check or generate ([checkers-si-emi](../topics/rules/checkers-si-emi.md)).
