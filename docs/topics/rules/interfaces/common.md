# Interface rule packs: shared rules

Scope: rules and conventions shared by every per-interface pack in this folder (vendor selection, check codes, skew as UI, loss budgets, chain order, AC caps, ESD, TI family-scoped tables). Not here: diff-pair physics -> [../diff-pairs.md](../diff-pairs.md); return paths, stubs, crosstalk -> [../si-fundamentals.md](../si-fundamentals.md); pack syntax and precedence -> [../rule-pack-format.md](../rule-pack-format.md).
Keys: interface pack, vendor profile, check codes K G S M, skew as UI, loss budget, chain order, AC coupling cap, pad void, ESD topology, TVS, TI SoC tables, family-scoped, microstrip vs stripline
Tags: [P] primary, [S] snippet, [I] inference, [VR] verification_rules.md.

## Interface docs
| Interface | Doc |
|---|---|
| USB 2.0 HS | [usb2.md](usb2.md) |
| USB 3.x / USB4 / Type-C | [usb3-usb4-typec.md](usb3-usb4-typec.md) |
| PCIe Gen2–6 | [pcie.md](pcie.md) |
| DDR3 / DDR4 / LPDDR4 | [ddr.md](ddr.md) |
| Ethernet BASE-T, RGMII/MII | [ethernet.md](ethernet.md) |
| HDMI / DisplayPort | [hdmi-dp.md](hdmi-dp.md) |
| MIPI D-PHY | [mipi.md](mipi.md) |
| SATA / UFS / SD | [sata-ufs-sd.md](sata-ufs-sd.md) |
| I2C / SPI / QSPI | [i2c-spi-qspi.md](i2c-spi-qspi.md) |
| CAN / RS-485 | [can-rs485.md](can-rs485.md) |

## Check-column codes
`K` KiCad DRC rule (`.kicad_dru`), `G` geometric checker, `S` solver/simulation (impedance, loss), `M` BOM/schematic check, `ask` user decision ([../rule-pack-format.md](../rule-pack-format.md)).

## Vendor profile selection
1. Vendor values differ by up to 14× (USB3 skew) or 12.5–25× (DDR). Select by the PHY/controller vendor profile; each interface doc lists defaults and `by_vendor` variants.
2. TI SoC tables (SPRAAR7J: AM57xx, KeyStone II, AM64x/65x, AM62x) are family-scoped [VR]: e.g. 0 vias on PCIe/SATA/HDMI for AM57xx/KeyStone vs 2 on AM64x/65x. Hard only for that family.
3. Unresolvable vendor conflicts (shield termination, ESD side of magnetics) → `ask`, log the choice.

## Skew as UI formula
Store budgets given as UI fractions (HDMI 0.15·Tbit, D-PHY UI/50 and 0.1 UI) as formulas; resolve to ps at the configured data rate; convert to mm through KiCad 10's per-layer delay; emit time-domain `skew`. Vendor ps-to-length constants (5–6.1 mil/ps) are not portable ([ddr.md#delay-to-length-conversions](ddr.md#delay-to-length-conversions)).

## Loss budget instead of length
SerDes (USB3, PCIe, UFS, MIPI): `L_max ≈ (budget − Σ via/cap/connector/ESD allowances) / (dB/in at Nyquist)` per stackup material [I]. Per-via allowance: ~1 in at 5 Gb/s (Heck), ~2 in at PCIe Gen2 (SLLU149E). Budgets and material tables: [pcie.md#pcie-loss-budget-ti-snla426](pcie.md#pcie-loss-budget-ti-snla426), [usb3-usb4-typec.md](usb3-usb4-typec.md), [mipi.md](mipi.md).

## Chain order and AC caps
- Path order is a hard placement intent: connector → ESD → (CMC) → AC cap → PHY (USB3; USB2 without the cap; CAN/RS-485: connector → TVS/CMC/filter → transceiver).
- AC caps: smallest package (0402, 0201 OK), symmetric pair side by side, never staggered or mid-line; plane void under pads (depth conflicts per interface); value window per interface (USB3 Gen2 75–265 nF, Gen1 75–200 nF, PCIe Gen3+ 176–220 nF, DP 75–265/75–200 nF, SATA ~10 nF, HDMI none).

## ESD and protection topology
TVS at the connector, no via or stub between connector and TVS pin, GND via adjacent to the TVS GND pin, corners ≤45°; physics (8 kV → 4×10¹⁰ A/s, 0.25 nH adds 10 V) -> [../emc-placement.md#tvs-topology](../emc-placement.md#tvs-topology). Exceptions: Ethernet ESD side of magnetics conflict ([ethernet.md](ethernet.md)); Type-C protection ([usb3-usb4-typec.md#type-c-rules](usb3-usb4-typec.md#type-c-rules)).

## Contested layer choice
Microstrip vs stripline for SerDes: TI SPRAAR7J "no stripline" vs Qualcomm inner layers, SNLA426/Efinix closely coupled stripline at Gen4–5 -> [../myths-and-contested.md](../myths-and-contested.md). Pack exposes a selector.

## Sources
- [interface_rule_packs.md](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md); [verification_rules.md](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
