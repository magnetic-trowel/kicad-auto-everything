# HDMI (TMDS) and DisplayPort layout rules

Scope: HDMI TMDS and DP main-link/AUX routing, AC caps, ESD. Not here: USB3/DP-alt rows -> [usb3-usb4-typec.md](usb3-usb4-typec.md); shared interface rules -> [common.md](common.md).
Keys: HDMI, TMDS, DisplayPort, DP, AUX, 0.15·Tbit, 0.20·Tchar, TMDS181, SN75DP159, TPD12S016, DP AC cap 265 nF
Tags: [P] primary, [S] snippet, [I] inference, [VR] verification_rules.md.

## HDMI vs DisplayPort rules table
| Param | HDMI | DisplayPort |
|---|---|---|
| Rates | 1.4b data to 1.7 GHz; 2.0b to 3 GHz; 2.1b to 6 GHz ([SLLA414A](https://www.ti.com/lit/pdf/slla414) [P]) | Up to 10 Gb/s per lane (Qualcomm table) |
| Impedance | 100 Ω ±15% (SLLA414A); TI AM57xx 90–110 Ω ([SPRAAR7J](https://www.ti.com/lit/pdf/spraar7)); Intel 100 Ω ±10% [S] | 100 Ω ±10% (SLLA414A) |
| AC coupling | **None allowed**; no polarity reversal | Required. **Conflict:** 75–200 nF (DP 1.2; TI SN75DP126, Diodes AN341 [S]) vs 75–265 nF ([TUSB1046](https://www.ti.com/lit/ds/symlink/tusb1046-dci.pdf) [P], maximum raised from 200 nF; [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb3dot1-displayport-routing-constraints.html) at 10 Gb/s; 75–200 nF at 5 Gb/s); 0402. Select by the sink's datasheet |
| Intra-pair skew | Source ≤0.15·Tbit (SLLA414A), ≈25 ps at 6 Gb/s [I]; TI SoC ≤5 mil | ≤20 ps (TI), ≈3 mm at 6–7 ps/mm (the note's "≈5 mil" is ≈0.8 ps) [I]; 5 ps ≈ 0.7 mm (Qualcomm) |
| Inter-pair skew | Source ≤0.20·Tcharacter; ADI ADV3003 keeps four channels within 0.05 in on FR4 [S] | 70 ps (10 mm) interlane; AUX intralane 50 ps (7 mm) (Qualcomm) |
| Length / vias | TI SoC: ≤4000 mil, **0 vias** [VR: family-scoped]; Intel ≤2 vias [S]. Retimers (TI [TMDS181](https://www.ti.com/lit/ds/symlink/tmds181.pdf), [SN75DP159](https://www.ti.com/lit/ds/symlink/sn75dp159.pdf)): TMDS on top layer to avoid vias; matched electrical length intra/inter-pair; solid GND next to signal layer, L1–L2 5–10 mil in the recommended 4/6-layer stacks; control signals on bottom | Use USB3/DP rows: ≤2 vias, return vias at transitions ([usb3-usb4-typec.md](usb3-usb4-typec.md)) |
| ESD | TI [TPD12S016](https://www.ti.com/lit/ds/symlink/tpd12s016.pdf): as close to connector as possible; unprotected traces away from protected; **no vias between connector and protection pins**; no 90° turns; minimal GND-path impedance | Generic ESD topology ([common.md#esd-and-protection-topology](common.md#esd-and-protection-topology)) |

## HDMI/DP checks to emit
- Skew as UI formula -> [common.md#skew-as-ui-formula](common.md#skew-as-ui-formula).
- BOM AC-cap check: HDMI none; DP 75–265 nF, or 75–200 nF for an older DP 1.2 sink.
- HDMI on TI SoCs: `via_count (max 0)` + top-layer net class.

## Open questions
- DP AC-cap maximum 200 vs 265 nF: select by part datasheet.
- HDMI Forum and VESA layout documents not accessible; no HDMI 2.1 FRL PCB budget found.

## Sources
- [interface_rule_packs.md § 5](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md); [verification_rules.md § 1A DP-2, DP-6](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- See also [mipi.md](mipi.md), [../diff-pairs.md](../diff-pairs.md).
