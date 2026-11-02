# CAN and RS-485 layout rules

Scope: CAN/RS-485 termination, stubs, failsafe, protection placement. Not here: generic ESD topology -> [common.md#esd-and-protection-topology](common.md#esd-and-protection-topology).
Keys: CAN, RS-485, ISO 11898, split termination, 120 ohm, 60 ohm, 4.7 nF, stub length, failsafe bias, 523 ohm, SLLA270, SLLA272D, TCAN1042H, CAN-TERM, 485-STUB
Tags: [P] primary, [S] snippet, [I] inference.

## CAN rules
Source: [TI SLLA270](https://www.ti.com/lit/pdf/slla270); [TCAN1042H](https://www.ti.com/lit/ds/symlink/tcan1042h.pdf) [P].

| Item | Value |
|---|---|
| ISO 11898 limits | 40 m at 1 Mb/s, ≤30 nodes, unterminated stub ≤0.3 m at 1 Mb/s |
| Cable length vs bit rate | 40 m @ 1 Mb/s; 100 m @ 0.5; 200 m @ 0.25; 500 m @ 0.10; 1000 m @ 0.05. Above 100 m: rate (Mb/s) × length (m) ≤ 50 |
| Termination | 120 Ω cable, 120 Ω at the two physical ends only. Not inside a removable node; on-board termination must not disappear when a node is removed |
| Split termination | ~60 Ω ±1% × 2 + typ. 4.7 nF (3 dB at 1.1 Mb/s). TCAN1042H datasheet tests with Rterm 60 Ω, Csplit 4.7 nF |
| Stub | ≤⅓ of critical length. 50 ns edge on 5 ns/m line → 5 m critical → 1.67 m stub; slope control 160 ns → ~5.3 m. On a PCB matters only for daisy-chained connectors |
| Protection layout | As close to bus connector as possible: bidirectional TVS or varistor; optional bus filter caps and CMC between transceiver and connector; protection "in the direction of the signal path" (do "not force the transient current to divert from the signal path"); ≥2 vias for VCC/GND of bypass caps and protection devices |

## RS-485 rules
Source: [TI SLLA272D](https://www.ti.com/lit/pdf/slla272) Rev. May 2021 [P].

| Item | Value |
|---|---|
| Termination | 120 Ω at each cable end; or 2 × 60 Ω as low-pass in noisy environments |
| Stub | Electrical length < 1/10 of driver 10/90 rise time: `L ≤ t_r·v·c/10`. At 78% velocity: 1 Mb/s / 100 ns → 7 ft; 250 kb/s / 250 ns → 19 ft; 200 kb/s / 500 ns → 38 ft |
| Failsafe bias | 2 × 523 Ω with 120 Ω terminations at 5 V ±5%. 32 unit loads, failsafe biasing worth up to 20 UL |
| Length × rate | length (m) × rate (b/s) < 10⁷ |
| PCB | Both lines close and equidistant (loose differential pair) |

## CAN/RS-485 rule IDs
| ID | Rule | Check |
|---|---|---|
| CAN-TERM | 120 Ω only at the 2 ends, or 2 × 60 Ω + 4.7 nF. Ask or infer end-node role; flag termination on a non-end node or missing on an end node | M: node role |
| CAN-PROT | Path order connector → TVS/CMC/filter → transceiver, hard topology ([../emc-placement.md](../emc-placement.md)); ≥2 vias on protection GND | G |
| CAN-STUB | ≤0.3 m at 1 Mb/s; ≤⅓ critical length | Calc; G checks daisy-chain T-junctions |
| 485-STUB | < t_r·v·c/10 | Calc + K `length` |
| 485-FS | 2 × 523 Ω failsafe on one node | M |

## Open questions
- No primary numeric TVS-to-connector distance found for CAN or RS-485.

## Sources
- [interface_rule_packs.md § 6](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
- See also [i2c-spi-qspi.md](i2c-spi-qspi.md).
