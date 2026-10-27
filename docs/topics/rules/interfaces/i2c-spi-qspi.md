# I2C, SPI/QSPI and slow multi-drop clocks

*Tags: [P] = primary source read; [S] = snippet only; [I] = our inference.*

**TL;DR**
- **I2C:** the rise-time and bus-capacitance limits set the pull-up window.
  - Limits: t_r ≤1000 / 300 / 120 ns and C_b ≤400 / 400 / 550 pF (Standard-mode / Fast-mode / Fast-mode Plus).
  - Pull-up window: R_P ∈ [(VCC − 0.4)/I_OL, t_r/(0.8473·C_b)], with I_OL = 3 / 3 / 20 mA (Sm / Fm / Fm+) [I; NXP UM10204].
  - We can check this automatically. Estimate C_b from the stackup's capacitance per mm plus the pin capacitances.
- **QSPI at 133 MHz (Infineon):** IO-to-IO ±30 mil, SCK-to-IO ±200 mil, and ±1500 mil. These are first-pass snippet values; check AN240090 for exactly what each tolerance applies to.
- **Slow multi-drop clocks (Qualcomm SLEEP_CLK):** star branches must differ by <30 mm; daisy-chain stubs must be <7 mm.
- **Fast-edge single-ended buses:**
  - Put a series R near the driver by default (LearnEMC).
  - Treat the net as electrically long at t_r/6 ([../si-fundamentals.md](../si-fundamentals.md)).

## Key facts

### I2C ([TI SLVA689A](https://www.ti.com/lit/pdf/slva689) Rev. Oct 2026 [P])

| Mode | t_r max | C_b max |
|---|---|---|
| Standard (Sm) | 1000 ns | 400 pF |
| Fast (Fm) | 300 ns | 400 pF |
| Fast-plus (Fm+) | 120 ns | 550 pF |

Pull-up bounds:
- Output low is VOL ≤0.4 V at 3 mA (Sm/Fm). Fm+ specifies 0.4 V at 20 mA [I; NXP UM10204]; with 3 mA the Fm+ window is empty (3.3 V, 300 pF: R_min 967 Ω > R_max 472 Ω), with 20 mA R_min is 145 Ω.
- R_P(min) = (VCC − VOL)/IOL.
- R_P(max) = t_r/(0.8473·C_b).

The numbers are TI's restatement; the NXP UM10204 specification itself was blocked.

### SPI / QSPI

| Item | Value | Source |
|---|---|---|
| QSPI at 133 MHz | IO ±30 mil, SCK–IO ±200 mil, ±1500 mil | [Infineon AN240090](https://www.infineon.com/assets/row/public/documents/10/42/infineon-an240090-design-and-layout-guide-for-cyrs17b-cyel17b-flash-quad-devices-applicationnotes-en.pdf) [S] |
| Series termination | Default to a series R on capacitively loaded digital nets, and remove it where it is clearly unnecessary. Use resistors, not ferrites | [LearnEMC](https://learnemc.com/pcb-layout) [P] |

### Slow multi-drop clocks

| Topology | Limit | Source |
|---|---|---|
| Star | Branches differ by <30 mm | [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/CXO-and-SLEEP_CLK-routing.html) [P] |
| Daisy chain | Stubs <7 mm | Qualcomm [P] |

LearnEMC says "Critical nets should be routed in a daisy chain fashion with no stubs" is only "sometimes" right [VR].

### Rule IDs

| ID | Rule | Check |
|---|---|---|
| I2C-RC | R_P within [(VCC−0.4)/I_OL, t_r/(0.8473·C_b)]; I_OL 3 mA (Sm/Fm), 20 mA (Fm+) | M + G (C_b from trace pF/mm + pins) |
| I2C-CB | C_b ≤400 pF (Sm/Fm), ≤550 pF (Fm+) | G/M |
| CLK-STAR | Branch Δ <30 mm; daisy stub <7 mm | G |

## Recommendations for our system
- Run an I2C pull-up and capacitance check: trace length × C′(stackup) + Σ pin capacitance → C_b → R_P window. This catches a common real-world failure.
- Treat QSPI as a matched group: SCK plus the IO lines, with skew in mm or ps. Put a series R at the flash controller's SCK.

## Conflicts and open questions
- The QSPI numbers are first-pass snippets, and the meaning of each tolerance needs re-reading in the source.
- No primary I2C specification was read; the numbers come via TI.

## Sources
- Research notes:
  - [interface_rule_packs.md § 6](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
  - [rules_highspeed_emi.md § 4](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)

See also:
- [can-rs485.md](can-rs485.md)
- [sata-ufs-sd.md](sata-ufs-sd.md)
- [../crystals-clocks.md](../crystals-clocks.md)
