# CAN and RS-485 layout rules

*Tags: [P] primary source read; [S] snippet only; [I] our inference.*

**TL;DR**
- **Termination.** Use 120 Ω at the two physical bus ends only.
  - CAN can instead use a split termination: 2 × 60 Ω ±1% plus 4.7 nF.
  - The termination must stay on the bus even if a node is removed.
- **Protection.** Put the TVS or varistor, any filter caps and the CMC at the connector, **in the signal path**. Do "not force the transient current to divert from the signal path". Use ≥2 vias on the protection and bypass grounds.
- **Stub limits depend on driver transition time.**
  - CAN: ≤⅓ of the critical length (ISO limit: 0.3 m at 1 Mb/s).
  - RS-485: electrical length <1/10 of the rise time.
  - On a PCB these matter only for daisy-chained connectors.
- **Local checks that matter on a PCB:** termination present only on end nodes, protection in the signal path, and both lines close together and equidistant.

## Key facts

### CAN ([TI SLLA270](https://www.ti.com/lit/pdf/slla270); [TCAN1042H](https://www.ti.com/lit/ds/symlink/tcan1042h.pdf) [P])

| Item | Value |
|---|---|
| ISO 11898 limits | 40 m at 1 Mb/s, ≤30 nodes, unterminated stub ≤0.3 m at 1 Mb/s |
| Cable length vs bit rate | 40 m @ 1 Mb/s; 100 m @ 0.5; 200 m @ 0.25; 500 m @ 0.10; 1000 m @ 0.05. Above 100 m: rate (Mb/s) × length (m) ≤ 50 |
| Termination | 120 Ω cable, terminated with 120 Ω at both ends. Don't put the termination inside a removable node; on-board termination must not disappear when a node is removed |
| Split termination | ~60 Ω ±1% × 2 with typ. 4.7 nF (3 dB at 1.1 Mb/s). The TCAN1042H datasheet tests with Rterm 60 Ω and Csplit 4.7 nF |
| Stub | ≤⅓ of the critical length. Example: a 50 ns edge on a 5 ns/m line gives a 5 m critical length, so a 1.67 m stub. With slope control at 160 ns, the stub can be ~5.3 m |
| Protection layout | As close to the bus connector as possible. Bidirectional TVS or varistor; optional bus filter caps and CMC between the transceiver and the connector. Protection "in the direction of the signal path". ≥2 vias for the VCC/GND of bypass caps and protection devices |

### RS-485 ([TI SLLA272D](https://www.ti.com/lit/pdf/slla272) Rev. May 2021 [P])

| Item | Value |
|---|---|
| Termination | 120 Ω at each cable end; or 2 × 60 Ω as a low-pass in noisy environments |
| Stub | Electrical length < 1/10 of the driver's 10/90 rise time: L ≤ t_r·v·c/10. At 78% velocity: 1 Mb/s / 100 ns → 7 ft; 250 kb/s / 250 ns → 19 ft; 200 kb/s / 500 ns → 38 ft |
| Failsafe bias | 2 × 523 Ω with 120 Ω terminations at 5 V ±5%. 32 unit loads, with failsafe biasing worth up to 20 UL |
| Length × rate | length (m) × rate (b/s) < 10⁷ |
| PCB | Keep both lines close and equidistant |

### Rule IDs

| ID | Rule | Check |
|---|---|---|
| CAN-TERM | 120 Ω only at the 2 ends, or 2 × 60 Ω + 4.7 nF | M: node role |
| CAN-PROT | TVS, filter and CMC at the connector, in the signal path; ≥2 vias on protection GND | G |
| CAN-STUB | ≤0.3 m at 1 Mb/s; ≤⅓ of the critical length | Calc; G checks daisy-chain T-junctions |
| 485-STUB | < t_r·v·c/10 | Calc + K `length` |
| 485-FS | 2 × 523 Ω failsafe on one node | M |

## Recommendations for our system
- **BOM / schematic check.** Ask the user, or infer from the system description, whether this node is an end node. Flag a termination on a non-end node, or a missing termination on an end node.
- **Placement intent.** Order the parts along the signal path: connector → TVS/CMC/filter → transceiver. Treat it as a hard topology rule ([../emc-placement.md](../emc-placement.md)).
- **Routing.** Route the pair close together and equidistant, as a loose differential pair. Board stubs are short enough to ignore unless connectors are daisy-chained.

## Conflicts and open questions
- **No primary numeric TVS-to-connector distance** was found for CAN or RS-485.

## Sources
- Research notes: [interface_rule_packs.md § 6](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)

See also: [i2c-spi-qspi.md](i2c-spi-qspi.md), [../emc-placement.md](../emc-placement.md)
