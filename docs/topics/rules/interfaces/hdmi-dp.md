# HDMI (TMDS) and DisplayPort layout rules

*Tags:*
- [P] primary source read
- [S] snippet only
- [I] our inference

**TL;DR**
- **HDMI TMDS**
  - 100 Ω ±15% (TI SoC tables ±10%), with **no AC caps** and no polarity reversal.
  - Skew is a fraction of the bit time: intra-pair ≤0.15·Tbit, inter-pair ≤0.20·Tchar. At 6 Gb/s that is about 25 ps intra-pair [I].
  - Store skew as a UI formula.
- **TI SoC (AM57xx) rules for TMDS**
  - ≤4000 mil length, ≤5 mil intra-pair, and **0 vias**.
  - Retimers route TMDS on the top layer, with L1–L2 spacing of 5–10 mil.
- **DisplayPort**
  - 100 Ω ±10%, with AC caps required.
  - Intra-pair ≤20 ps (TI); Qualcomm gives 5 ps intra, 70 ps inter-lane, 50 ps AUX.
  - AC cap value is either 75–200 nF (DP 1.2 practice) or 75–265 nF (newer TI parts, Qualcomm at 10 Gb/s).
- **HDMI ESD:** place it at the connector, with no vias between the connector and the protection pins and no 90° turns.

## Key facts
| Param | HDMI | DisplayPort |
|---|---|---|
| Rates | 1.4b data to 1.7 GHz; 2.0b to 3 GHz; 2.1b to 6 GHz ([SLLA414A](https://www.ti.com/lit/pdf/slla414) [P]) | Up to 10 Gb/s per lane (Qualcomm table) |
| Impedance | 100 Ω ±15% (SLLA414A); TI AM57xx 90–110 Ω ([SPRAAR7J](https://www.ti.com/lit/pdf/spraar7)); Intel 100 Ω ±10% [S] | 100 Ω ±10% (SLLA414A) |
| AC coupling | **None allowed**; no polarity reversal | Required. **Conflict:** 75–200 nF (DP 1.2; TI SN75DP126 and Diodes AN341 [S]) vs 75–265 nF ([TUSB1046](https://www.ti.com/lit/ds/symlink/tusb1046-dci.pdf) [P], which raised its maximum from 200 nF; [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb3dot1-displayport-routing-constraints.html) for 10 Gb/s; 75–200 nF for 5 Gb/s); 0402 |
| Intra-pair skew | Source ≤0.15·Tbit (SLLA414A); TI SoC ≤5 mil | ≤20 ps (TI), ≈3 mm at 6–7 ps/mm (the note's "≈5 mil" is ≈0.8 ps) [I]; 5 ps ≈ 0.7 mm (Qualcomm) |
| Inter-pair skew | Source ≤0.20·Tcharacter; ADI ADV3003 keeps the four channels within 0.05 in on FR4 [S] | 70 ps (10 mm) interlane; AUX intralane 50 ps (7 mm) (Qualcomm) |
| Length / vias | TI SoC: ≤4000 mil, **0 vias** [VR: family-scoped]; Intel ≤2 vias [S]. Retimers (TI [TMDS181](https://www.ti.com/lit/ds/symlink/tmds181.pdf), [SN75DP159](https://www.ti.com/lit/ds/symlink/sn75dp159.pdf)): TMDS on the top layer to avoid vias; matched electrical length for intra- and inter-pair skew; solid GND next to the signal layer, with L1–L2 5–10 mil in the recommended 4- and 6-layer stacks; control signals on the bottom layer | Use USB3/DP rows: ≤2 vias, return vias at transitions ([usb3-usb4-typec.md](usb3-usb4-typec.md)) |
| ESD | TI [TPD12S016](https://www.ti.com/lit/ds/symlink/tpd12s016.pdf): as close to the connector as possible; keep unprotected traces away from protected ones; **no vias between the connector and the protection pins**; no 90° turns; minimal GND-path impedance | Generic ESD topology ([../emc-placement.md](../emc-placement.md)) |

## Recommendations for our system
- **Store skew as a UI formula.** Keep the HDMI and D-PHY budgets as UI fractions, resolve them to ps at the configured data rate, then convert to mm through KiCad 10's per-layer delay. Emit time-domain `skew`.
- **Run an AC-cap BOM check:**
  - HDMI: there must be none.
  - DP: 75–265 nF, or 75–200 nF if the sink is an older DP 1.2 part.
- **HDMI on TI SoCs:** add `via_count (max 0)` and a top-layer net class.

## Conflicts and open questions
- **DP AC-cap maximum:** 200 nF vs 265 nF. Select by the part's datasheet.
- **Missing primary sources:**
  - HDMI Forum and VESA layout documents were not accessible.
  - No HDMI 2.1 FRL PCB budget was found.

## Sources
- research notes: [interface_rule_packs.md § 5](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
- [verification_rules.md § 1A DP-2, DP-6](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also:
- [usb3-usb4-typec.md](usb3-usb4-typec.md)
- [mipi.md](mipi.md)
- [../diff-pairs.md](../diff-pairs.md)
