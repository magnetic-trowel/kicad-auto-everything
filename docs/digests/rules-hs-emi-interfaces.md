# Digest: high-speed, SI, EMC, stackup and interface rules

This digest summarises three research notes: `rules_highspeed_emi.md`, `interface_rule_packs.md` and the high-speed/EMC parts of `verification_rules.md`. Where the verification note corrects the other two, the corrections win. Detail lives in the topic docs linked from each statement. The full idea list is in [inventory-rules-hs-emi.md](../ideas/inventory-rules-hs-emi.md).

## Physics (the "why")
- **One shared model.** Ott, Hubing, Bogatin, Johnson, Hartley and Archambeault agree: high-frequency return current flows in the adjacent plane, directly under the trace. EMI comes mainly from common-mode voltage between cables or chassis, and from imbalance or skew. So the system should encode physics, not slogans. See [si-fundamentals](../topics/rules/si-fundamentals.md) and [emc-placement](../topics/rules/emc-placement.md).
- **Return-path rules:**
  - Every fast net, and each leg of a differential pair, needs continuous reference copper.
  - Follow Ott's layer-change order.
  - Place a return via within ≤200 mil, scaled with data rate (down to about 1.3 mm at PCIe Gen5).
  - Use stitching caps (≤1 µF) only at unavoidable split crossings.
  - Merged antipads act as slots.
  
  Details: [si-fundamentals](../topics/rules/si-fundamentals.md).
- **Timing is set by rise time, not clock period.**
  - Flag a net for SI review at t_r/6; it must be terminated at t_r/2 (contested threshold).
  - Slow the edges before terminating.
  - Keep stubs below min(15 mil, 0.3/Gbps).
  - Crosstalk follows K = 1/(1+(D/H)²), so reduce h first.
  
  Details: [si-fundamentals](../topics/rules/si-fundamentals.md).
- **EMC thresholds:**
  - About 1 mV between antenna parts can fail Class B.
  - Cable common-mode current limits: 5 µA (Class B) and 15 µA (Class A).
  - LearnEMC's MREMC algorithm turns "no high-speed circuitry between connectors" into a computable estimate.
  
  Details: [emc-placement](../topics/rules/emc-placement.md).

## Stackup and differential pairs
- **Stackup:**
  - Choose it before placement, using Ott's five objectives, a candidate library and an 8-step scorer.
  - Ott and Hartley disagree on the common 6-layer stack, and TI and Ott disagree on stripline. Both are warnings with a selector, not rejections.
  
  Details: [stackup](../topics/rules/stackup.md).
- **Differential pairs:**
  - Pairs are not self-returning.
  - 20% skew produces 10% common mode. Budget skew as min(spec, 0.1·t_r), with running-skew compensation.
  - Coupling tighter than 0.5 mm buys no extra EMI benefit.
  - TI's keep-outs: 30 mil to other signals and 50 mil to clocks.
  - The verification note corrects the uncoupled-length limit to ≤45 mil, and replaces jog "amplitude" with a maximum spread.
  
  Details: [diff-pairs](../topics/rules/diff-pairs.md).

## Interfaces (vendor-keyed)
- **Vendor values differ 5–25×.** Examples: USB3 skew 2 mil vs 0.7 mm; DDR4 DQ↔DQS 2 ps vs 25 ps; Ethernet PHY↔magnetics ≥25 mm vs <25 mm. Vendor profiles are mandatory; when the vendor is unknown, default to the tightest primary value. See [rule-pack-format](../topics/rules/rule-pack-format.md).
- **Per-interface packs**, with loss budgets in place of length limits wherever possible:
  - [USB 2.0](../topics/rules/interfaces/usb2.md)
  - [USB3/USB4/Type-C](../topics/rules/interfaces/usb3-usb4-typec.md): connector → ESD → CMC → AC cap → PHY
  - [PCIe](../topics/rules/interfaces/pcie.md): TI loss budgets; 220 nF AC caps
  - [DDR](../topics/rules/interfaces/ddr.md): one `fromTo` rule per SDRAM; byte-only matching; 20% derating
  - [Ethernet](../topics/rules/interfaces/ethernet.md)
  - [HDMI/DP](../topics/rules/interfaces/hdmi-dp.md)
  - [MIPI](../topics/rules/interfaces/mipi.md): cable-loss input
  - [SATA/UFS/SD](../topics/rules/interfaces/sata-ufs-sd.md)
  - [CAN/RS-485](../topics/rules/interfaces/can-rs485.md)
  - [I2C/SPI/QSPI](../topics/rules/interfaces/i2c-spi-qspi.md)
- **Crystals:**
  - Place in an annulus: a vendor-specific minimum distance (Espressif ≥2.0–2.7 mm) up to a ≤12 mm maximum.
  - Score parasitic capacitance.
  - Vendors conflict on metal-can grounding and on copper under the crystal.
  
  Details: [crystals-clocks](../topics/rules/crystals-clocks.md).
- **Buck regulators and fab limits** belong to the power cluster: [power/buck](../topics/rules/power/buck.md), [dfm-fab-limits](../topics/rules/dfm-fab-limits.md).

## EMC placement
- **Placement rules:**
  - Cabled connectors on one edge or corner.
  - No high-speed circuitry between connectors.
  - I/O device within about 2 cm of its connector; other parts at least 2 cm away.
  - A 7-step placement order: steps 1–3 hard, 4–6 soft cost terms.
  
  Details: [emc-placement](../topics/rules/emc-placement.md).
- **TVS and CMC placement:**
  - TI gives no millimetre distance. Encode connector → TVS → IC as comparative constraints: no via or stub before the TVS, and a GND via at its pad.
  - ESD-path corners ≤45°.
  - Edges: ≥90 mil from the plane edge and ≥2h from the board edge.
  - Stitching (perimeter vs distributed) is contested, so use a "largest unstitched region" metric instead.
  
  Details: [emc-placement](../topics/rules/emc-placement.md).

## How rules are classified and encoded
- **Myths and contested rules:**
  - Famous myths (90° corners, 20-H, split grounds, 3W, guard traces) become negative rules that each carry their physics replacement.
  - Contested rules are never emitted as defaults.
  
  Details: [myths-and-contested](../topics/rules/myths-and-contested.md).
- **Rule tiers:** hard fab limits; hard topology; hard within a declared scope; soft-strong; soft-weak; context switch.
  - Millimetre values that appear only in blogs become rank objectives.
  - Records carry `source_scope`, `statement_strength` and `contested_by`.
  
  Details: [rule-pack-format](../topics/rules/rule-pack-format.md).
- **Rule packs:** a YAML format with precedence fab 10 < interface 20 < vendor 30 < datasheet 40, `by_vendor` values, recorded conflicts, and the rule that [S] never overrides [P]. Details: [rule-pack-format](../topics/rules/rule-pack-format.md).
- **What KiCad covers natively:**
  - KiCad 10: ps delay, `fromTo` and backdrill.
  - KiCad master: `return_path`, `stub_length`, net chains and via stitching.
  
  Details: [checkers-si-emi](../topics/rules/checkers-si-emi.md).
- **Custom checkers A–I** cover the rest: reference map, return continuity, reference change, via stubs, connector placement, crosstalk, stitching, protection topology and loop ranking. Details: [checkers-si-emi](../topics/rules/checkers-si-emi.md).
- **Reusing existing checkers.** With GPL-3.0-or-later code, these can be reused: kicad-happy and EMI Guardian (MIT), emcvisual (0BSD-style), RF-tools (GPL-3.0). The `return_path` checker and EMC Auditor are reference only. Details: [checkers-si-emi](../topics/rules/checkers-si-emi.md).
- **The gap.** No public tool closes the loop (generate constraints → route → physics-check) inside KiCad; every existing tool only checks or generates. Details: [checkers-si-emi](../topics/rules/checkers-si-emi.md).
