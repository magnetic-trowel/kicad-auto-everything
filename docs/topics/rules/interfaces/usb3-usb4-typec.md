# USB 3.x SuperSpeed, USB4 and USB Type-C (CC, SBU, protection, orientation mux)

*Tags:*
- [P] primary source read
- [S] snippet only
- [I] our inference

**TL;DR**
- **Intra-pair skew is where vendors diverge most:**
  - 2–2.5 mil (TUSB1046, TUSB9261);
  - 5 mil (TI SPRAAR7J, Microchip, SLLU149E);
  - 5 ps ≈ 0.7 mm (Qualcomm), about 6× looser.
  
  Default to 5 mil, override by vendor profile, and keep Qualcomm's figure as the "physics-justified relaxed" option.
- **Common ground across vendors:**
  - ≤2 vias per trace, with GND return vias at each layer change;
  - 75–265 nF TX AC caps (75–200 nF for Gen1), 0402 or smaller, symmetric, with a reference-plane void under the pads;
  - chain order **connector → ESD → CMC → AC cap → PHY**.
- **Use loss budgets, not lengths.** Connector-to-PHY: Gen1 −5.5 dB at 2.5 GHz, Gen2 −7 dB at 5 GHz (Qualcomm). Each via costs about 1 in of routing, and ESD+CMC costs about 1 in (Heck).
- **Type-C CC:**
  - traces ≥8 mil (VCONN up to 600 mA);
  - total capacitance 200–600 pF;
  - **no passives** between the PD controller and the receptacle [S];
  - protection at the receptacle, with no via between the connector and the TVS pin.
- **USB4 has no primary PCB numbers**; only snippets exist.

## Key facts
| Param | Default | Variants / **conflicts** | Check |
|---|---|---|---|
| Rates | Gen1 5 Gb/s (2.5 GHz), Gen2 10 Gb/s (5 GHz), USB4 Gen3 20 Gb/s NRZ (10 GHz), Gen4 40 Gb/s PAM3 (20 GHz). AC caps required on TX, optional on RX; SSTX/SSRX polarity reversal allowed; 3 m cable ([SLLA414A](https://www.ti.com/lit/pdf/slla414) [P]) | — | — |
| Zdiff | 90 Ω ±15% / 45 Ω SE (SLLA414A, TUSB9261, TUSB1046, SLLU149E) | AM57xx 83.7–96.3 Ω; AM65xx 95 Ω ±5%; Microchip AN26.2 85 ±5 Ω; Qualcomm 70–100 Ω incl. manufacturing variation | K + S |
| Intra-pair skew | 5 mil (0.127 mm): SPRAAR7J tables, AN26.2 (0.13 mm), SLLU149E; SLLA414A "15 ps/m (TI recommends 5 mils)" | [TUSB1046](https://www.ti.com/lit/ds/symlink/tusb1046-dci.pdf) 2 mil; [TUSB9261](https://www.ti.com/lit/ds/symlink/tusb9261.pdf) 2.5 mil; [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb3dot1-displayport-routing-constraints.html) 5 ps ≈ 0.7 mm (27.5 mil). 5 mil ≈ 0.75–0.9 ps [I] | K `skew within_diff_pairs` (device override) |
| Inter-lane / DP AUX | 70 ps (10 mm) / 50 ps (7 mm) intralane (Qualcomm) | — | K |
| Loss | Connector→PHY: Gen1 ≤5.5 dB at 2.5 GHz; Gen2 ≤7 dB at 5 GHz (Qualcomm) | Heck: channel −6 to −20 dB, cable ≤7.5 dB | S: Σ length × dB/in + via/cap allowances |
| Vias | ≤2 per trace (SPRAAR7J; TUSB1046 "2 or less"; Qualcomm "no more than two core vias"); complementary GND vias at every SS layer change (AN26.2) | Heck: stub reflections "cost up to 1 in of routing per via"; bottom-side connector entry | K `via_count (max 2)`; G return-via test |
| Layer | Qualcomm: route pairs on inner layers with solid GND, isolated from 2.4 GHz antennas | **Conflict with TI SPRAAR7J "no stripline"** (see [../myths-and-contested.md](../myths-and-contested.md)) | selector |
| Max length | 3500 mil (88.9 mm, AM57xx); 5500 mil (KeyStone II); 4000 mil (AM65xx); TUSB7340 "no longer than eight inches" (compliance channel) | Heck: host PCB 2–12 in, device 1–4 in (keep device ≤2 in); ESD+CMC "reduces max route length by ~1 in" | K `length`; S |
| Spacing | 5W between SS TX/RX pairs and to DP/DM (e.g. 5 mil → 25 mil air gap); 30 mil keep-out to other signals; 50 mil to clocks (TUSB9261, HD3SS3220, SPRAAR7J) | TUSB1046 ≥3W; Qualcomm Rx-Tx 4W (Gen2) / 3W (Gen1), 4W to others; Microchip ≥5X (7 mil → 35 mil). If impossible: ground fill, or route on opposite sides of GND (TUSB9261) | K `clearance` |
| AC cap value | 75–265 nF Gen2 (Qualcomm; TUSB1046 table, whose DP RX maximum was revised 200 → 265 nF); 75–200 nF Gen1 (Qualcomm) | TUSB9261/TUSB7340 0.1 µF; Type-C redrivers 220 nF TX (+330 nF RX) [S] | M |
| AC cap package and pad | ≤0603 maximum, 0402 "strongly recommended" (0201 OK); "no bigger than 0402, C-packs not allowed"; symmetric, near the connector pins | **Pad-void conflict:** SLLA414A 100%, ≥2 layers deep; SPRAAR7J 60% under ESD/EMI signal pads; Heck 100% under CMC and ESD | M; G zone keep-out |
| Chain order | connector → ESD → CMC → AC cap → PHY (TUSB9261/SLLU149E: ESD "closer than the choke and transmitter capacitors"; SPRAAR7J: AC caps on the protected side of the CMF; Qualcomm: TX caps "close to source or the ESD/connector side") | TUSB1002A: cap ≥0.25 in (6.35 mm) from the redriver [S] | G: path order and distances |
| CMC option | Heck: 100% voids under CMC and ESD; 0402 0 Ω no-stuff alternative to the CMC | — | G |
| Bends and symmetry | Bends ≥135°, balanced left/right; all pairs on the same layer; test points only in series and symmetric, never stubs (TUSB1046) | — | K `track_angle` / G |
| Adjacent layers | Route at a 90° offset (HD3SS3220) | — | G |
| USB4 | [S] only: 85 Ω ±7%, skew <3 mil, ~60 mm. Link-partner budget 8.5 → 5.5 dB at 10G. A Gen2 8.5 dB host budget ≈ 5 in of trace | No primary source found | low confidence |

### Type-C specifics
| Item | Rule | Source |
|---|---|---|
| CC width | ≥8 mil (0.2 mm) for VCONN, up to 600 mA with Ra present. TPS65988DK minimums: CC1/CC2/PP_CABLE 8 mil, VIN_3V3/LDO 6, component GND 10, GPIO 4; capacitor GND pin 16 mil where possible | TI TPS65987D/88DK [S] |
| CC capacitance | cReceiver 200–600 pF (controller + protection + external cap; USB PD §5.8.6). TPD6S300A example: 220 pF 0201 X7R with ±50% temperature budget | [TI TPD6S300A](https://www.ti.com/document-viewer/TPD6S300A/datasheet/cc-line-capacitance-t4582032-9) [S] |
| CC direct connection | Connect CC directly from the PD controller to the receptacle, with no 0 Ω or other passives | [TI SLVA888C](https://www.ti.com/document-viewer/lit/html/SLVA888C/GUID-00F49BD1-806B-4083-9CBB-C3D4B1A79D6E) [S] |
| CC/SBU/D± protection | TPD6S300A as close to the connector as possible; unprotected traces kept away from protected ones; USB2 and SBU as straight as possible with the largest-radius corners; do not via onto D1/D2 pins from another layer (via first, then continue on the pin's layer); VBIAS 0.1 µF; VPWR bypass close to the pin on solid ground | [TPD6S300A §11](https://www.ti.com/lit/ds/symlink/tpd6s300a.pdf) [P] |
| ESD physics | 8 kV → 4×10¹⁰ A/s, so 0.25 nH adds 10 V. No via between the source and the TVS. GND via immediately adjacent to the TVS GND. Corners ≤45° (arcs below ~2.6 mm radius) | [SLVA680A](https://www.ti.com/lit/pdf/slva680) [P; VERIFIED topology] |
| Orientation mux | TUSB1046 layout example: connector → AC caps → redriver for the SS lanes. Vendor blogs disagree on whether the CMC precedes the mux. No numeric mux-to-receptacle distance | [TUSB1046 Fig. 10-1](https://www.ti.com/lit/ds/symlink/tusb1046-dci.pdf) [P]; blog [S] |

## Recommendations for our system
- **Skew.** Default to 5 mil, override by the PHY/redriver vendor profile, and keep the 5 ps option as relaxed. Emit `skew` in ps (KiCad 10) where the vendor specifies time.
- **Placer cost.** Add about 25 mm of equivalent length per via and about 25 mm for ESD+CMC on SerDes channels [I] (from Heck). Check the loss budget with per-material dB/in.
- **Chain order.** Enforce connector → ESD → CMC → AC cap → PHY as a hard path-order intent. Also require symmetric caps, a void under the pads, and GND return vias at each transition.
- **Type-C.** CC width class ≥0.2 mm; BOM check for the capacitance window and for no series parts on CC.

## Conflicts and open questions
- **Intra-pair skew:** up to 14× vendor spread.
- **Pad-void depth:** 100% vs 60%.
- **Inner-layer (Qualcomm) vs outer-layer (TI) routing.**
- **CMC-before-mux.**
- **Missing primary sources:** no USB-IF/USB4 primary channel budgets and no SBU numeric rule were found.

## Sources
- Research notes:
  - [interface_rule_packs.md § 1](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
  - [verification_rules.md § 1A DP-2, DP-5, DP-6](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- Heck, USB-IF DevCon (partly legible): https://community.infineon.com/gfawx74859/attachments/gfawx74859/usb-superspeed-peripherals/18243/1/2-4_SSUSB_DevCon_DesignGuidelines_Heck.pdf

See also:
- [usb2.md](usb2.md)
- [hdmi-dp.md](hdmi-dp.md)
- [../diff-pairs.md](../diff-pairs.md)
- [../emc-placement.md](../emc-placement.md)
