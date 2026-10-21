# SATA, UFS and SD/SDIO/eMMC layout rules

*Tags: [P] primary source read; [S] snippet only; [I] our inference.*

**TL;DR**
- **SATA.** 100 Ω ±15%. Intra-pair skew ≤2.5 mil (TUSB9261) or ≤5 mil (TI SoC). AC caps of about 10 nF, ≤0402, placed near the connector. 0 vias on TI SoC tables.
  - **P/N swap is controller-dependent:** TUSB9261 allows it; LattePanda says no inversion.
- **UFS (Qualcomm).** Intralane skew 5 ps (0.7 mm); TX1↔TX2 or RX1↔RX2 skew 30 ps (4.2 mm).
  - Gear 3: 6 Gb/s, −6 dB at 3 GHz, ≤150 mm.
  - Gear 4: 10 Gb/s, −5.0 dB at 5.8 GHz, ≤70 mm.
- **SD (Qualcomm).** Clock-to-data matching and bus length scale with speed:
  - 50 MHz: 6 mm matching, bus <150 mm.
  - 208 MHz: 2 mm matching, bus <50 mm.
  - Series R of 18–27 Ω on CLK at the source.
- **SDIO (Espressif).** CMD and DATA within ±50 mil of CLK; ≤2000 mil total; CLK surrounded by GND; 50 Ω ±10%.

## Key facts

### SATA
| Param | Value | Source |
|---|---|---|
| Impedance | 100 Ω ±15% | [TI TUSB9261](https://www.ti.com/lit/ds/symlink/tusb9261.pdf) [P] |
| Impedance (TI SoC) | 85–115 Ω | [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P] |
| Intra-pair skew | ≤2.5 mil (TUSB9261); ≤5 mil (SPRAAR7J) | [P] |
| Length / vias (TI SoC) | ≤3500 mil (AM57xx) or ≤5500 mil (KeyStone II); **0 vias** (family-scoped) | SPRAAR7J [VR] |
| AC caps | Inline caps ≤0402, no C-packs, symmetric and close to the SATA connector (TUSB9261). Values: 0.3–12 nF, typ. 10 nF, on TX and RX (TI TDA2 [S]). Caps within ~10 mm of the connector (LattePanda [S]) | [P]/[S] |
| TX↔RX spacing | 5W | TUSB9261 |
| **Polarity** | TUSB9261: "permissible to swap the plus and minus on the SATA differential pair", but never TX with RX. **Conflict:** LattePanda says no polarity inversion [S] | Controller-dependent |

### UFS ([Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/UFS%20routing%20constraints.html) [P])
| Param | Gear 3 (6 Gb/s) | Gear 4 (10 Gb/s) |
|---|---|---|
| Channel loss | −6 dB at 3 GHz | −1.3 dB at 2.9 GHz; −5.0 dB at 5.8 GHz |
| Bus length | 25 / 75 / 150 mm | ≤70 mm |
| Zdiff | 75–105 Ω | 70–110 Ω |
| Intralane skew | 5 ps (0.7 mm) | 5 ps (0.7 mm) |
| TX1↔TX2 / RX1↔RX2 skew | 30 ps (4.2 mm) | 30 ps (4.2 mm) |
| Spacing | RX-to-TX 1.5–3 × W; others 2–3 × W | same |

### SD / SDIO / eMMC
| Param | Value | Source |
|---|---|---|
| SD at 50 MHz DDR / 100 MHz SDR | Card load 10 pF; bus <150 mm; clock-to-data 6 mm | [Qualcomm SDC2](https://docs.qualcomm.com/doc/80-PV086-5P/topic/SDC2%20external%20SD%20card%20routing%20constraints.html) [P] |
| SD at 208 MHz (SDR104) | 5 pF; bus <50 mm; clock-to-data 2 mm | Qualcomm [P] |
| Spacing / termination | 1.5 × W; CLK series termination 18–27 Ω | Qualcomm [P] |
| SDIO (ESP32-S3) | CMD/DATA0–3 within ±50 mil of SDIO_CLK; total ideally within 2000 mil; CLK surrounded by ground; 50 Ω ±10% | [Espressif](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html) [P]; [VR] |

### Rule IDs for emission
| ID | Rule | Check |
|---|---|---|
| SATA-ACV | 10 nF TX/RX caps, ≤0402, near the connector | M + G |
| SATA-SKEW | 0.064–0.127 mm; 0 vias (TI SoC) | K |
| UFS-SKEW | 0.7 mm intralane / 4.2 mm lane-to-lane | K |
| SD-MATCH | CLK↔DATA/CMD ≤6 mm / ≤2 mm; Espressif ±1.27 mm | K `skew` |
| SD-LEN | <150 mm / <50 mm; Espressif ≤50.8 mm | K `length` |
| SD-RS | 18–27 Ω CLK series R at the source | M + G (R near the driver) |

## Recommendations for our system
- **Polarity swap.** Make SATA P/N swap a controller-profile flag that the router may use only when the flag allows it.
- **Matching rules.** Express SD and SDIO matching as `skew` rules on the CLK + CMD/DATA group.
- **Series resistor placement.** Place the CLK series R at the driver (placement intent `adjacent`).

## Conflicts and open questions
- **SATA polarity rules differ by controller.** Some cap values are only [S].
- **No primary SD Association layout document was read.**

## Sources
- research notes: [interface_rule_packs.md § 5, 6](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)

See also:
- [../diff-pairs.md](../diff-pairs.md)
- [pcie.md](pcie.md)
- [i2c-spi-qspi.md](i2c-spi-qspi.md)
