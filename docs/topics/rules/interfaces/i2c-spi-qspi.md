# I2C, SPI/QSPI and slow multi-drop clocks

Scope: I2C pull-up/capacitance window, QSPI matching, star/daisy clock limits, series termination of SE buses. Not here: crystals -> [../crystals-clocks.md](../crystals-clocks.md); electrical-length rule -> [../si-fundamentals.md](../si-fundamentals.md).
Keys: I2C, SPI, QSPI, pull-up, R_P, C_b, t_r, Fm+, UM10204, SLVA689A, AN240090, SLEEP_CLK, star, daisy chain, series termination, I2C-RC, CLK-STAR
Tags: [P] primary, [S] snippet, [I] inference, [VR] verification_rules.md.

## I2C rise-time and bus-capacitance limits
Source: [TI SLVA689A](https://www.ti.com/lit/pdf/slva689) Rev. Oct 2026 [P] (TI's restatement; NXP UM10204 itself was blocked).

| Mode | t_r max | C_b max | I_OL at VOL 0.4 V |
|---|---|---|---|
| Standard (Sm) | 1000 ns | 400 pF | 3 mA |
| Fast (Fm) | 300 ns | 400 pF | 3 mA |
| Fast-plus (Fm+) | 120 ns | 550 pF | 20 mA [I; NXP UM10204] |

- `R_P(min) = (VCC − VOL)/I_OL`, `R_P(max) = t_r/(0.8473·C_b)`.
- Fm+ with 3 mA gives an empty window (3.3 V, 300 pF: R_min 967 Ω > R_max 472 Ω); with 20 mA R_min = 145 Ω.
- Check: C_b = trace length × C′(stackup pF/mm) + Σ pin capacitance → R_P window. Catches a common real-world failure.

## SPI / QSPI rules
| Item | Value | Source |
|---|---|---|
| QSPI at 133 MHz | IO-to-IO ±30 mil, SCK–IO ±200 mil, ±1500 mil (first-pass snippet; re-read what each tolerance applies to) | [Infineon AN240090](https://www.infineon.com/assets/row/public/documents/10/42/infineon-an240090-design-and-layout-guide-for-cyrs17b-cyel17b-flash-quad-devices-applicationnotes-en.pdf) [S] |
| QSPI group | Matched group SCK + IO lines, skew in mm or ps; series R at the flash controller's SCK | [I] |
| Series termination | Default series R near the driver on capacitively loaded digital nets; remove where clearly unnecessary. Resistors, not ferrites. Net is electrically long at t_r/6 | [LearnEMC](https://learnemc.com/pcb-layout) [P] |

## Slow multi-drop clock topology limits
| Topology | Limit | Source |
|---|---|---|
| Star | Branches differ by <30 mm | [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/CXO-and-SLEEP_CLK-routing.html) [P] (SLEEP_CLK) |
| Daisy chain | Stubs <7 mm | Qualcomm [P] |

LearnEMC "Critical nets should be routed in a daisy chain fashion with no stubs" is only "sometimes" right [VR].

## I2C/SPI rule IDs
| ID | Rule | Check |
|---|---|---|
| I2C-RC | R_P within [(VCC−0.4)/I_OL, t_r/(0.8473·C_b)]; I_OL 3 mA (Sm/Fm), 20 mA (Fm+) | M + G (C_b from trace pF/mm + pins) |
| I2C-CB | C_b ≤400 pF (Sm/Fm), ≤550 pF (Fm+) | G/M |
| CLK-STAR | Branch Δ <30 mm; daisy stub <7 mm | G |

## Open questions
- QSPI numbers are first-pass snippets.
- No primary I2C specification read; numbers via TI.

## Sources
- [interface_rule_packs.md § 6](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md); [rules_highspeed_emi.md § 4](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)
- See also [can-rs485.md](can-rs485.md), [sata-ufs-sd.md](sata-ufs-sd.md).
