# Interface- and Circuit-Specific Numeric Layout Rule Packs (supplement to rules_highspeed_emi.md and rules_power_rf_analog_dfm.md)

Scope: fills the numeric gaps left by the two earlier rule catalogs, plus a proposed rule-pack format. Topics covered:
- USB 2.0/3.x/USB4 and USB-C
- PCIe Gen2–6
- DDR3/DDR4/LPDDR4 tables
- Ethernet, HDMI, DisplayPort, MIPI, SATA, UFS
- SD/SDIO, CAN, RS-485, I2C
- Crystals
- Switching-regulator loop and placement numbers
- Board-edge and return-via rules
- Fab, assembly and mounting-hole limits

Provenance tags on every number:
- **[P]**: read in this session from the primary document. That means a vendor PDF, datasheet or official documentation page, fetched with curl and converted with pdftotext or an HTML-to-text pass. The document revision is given where the document prints one.
- **[S]**: search-result snippet only, because the page could not be fetched or is JavaScript-rendered. Lower confidence.
- **[D]**: derived or computed by me from cited numbers. The source does not state it.

Units: 1 mil = 0.0254 mm. Where a source gives mils, mm are added in parentheses. W = trace width; H or RPH = height of the trace above its reference plane; UI = unit interval.

Check-type codes used in the "Auto-check" columns:
- **K**: native KiCad custom-rule constraint. KiCad 10 constraint names include `length`, `skew` (with `within_diff_pairs`), `via_count`, `diff_pair_gap`, `diff_pair_uncoupled`, `edge_clearance`, `clearance`, `track_width`, `hole_size`, `annular_width`, `text_height`, `text_thickness`, `silk_clearance`, `courtyard_clearance`, `hole_to_hole`, `physical_clearance`, `via_diameter` and `disallow`.
  - KiCad 10 supports pad-to-pad path conditions, e.g. `A.fromTo('U1-A*','U2-B*')`.
  - It also supports time units (`ps`) in `length` and `skew`. Using them switches the tuner to the time domain, with per-layer unit delay and via delay.
  - Sources: [KiCad 10.0 PCB Editor, custom rules](https://docs.kicad.org/10.0/en/pcbnew/pcbnew_advanced.html) and [KiCad 10.0 PCB Editor, time-domain tuning](https://docs.kicad.org/10.0/en/pcbnew/pcbnew_editing.html) [P, read from the 10.0 documentation source].
- **G**: geometric check against the board model (pcbnew Python / IPC API). Examples: pad distances, polygon areas, plane-edge offsets, topology order.
- **S**: needs SI/PI simulation or a loss calculator. The rule pack carries only the budget.
- **M**: schematic/BOM check (value, package, rating), not geometric.

Source corpus read in full or in the relevant sections this session:
- **TI:**
  - Interface guides: SPRAAR7J, SPRAAR7A (2013), SLLA414A, SNLA426, SLLU149E.
  - Memory: SPRABI1D, SPRAD06C.
  - Ethernet: SNLA387, SNLA079D (AN-1469), DP83867 datasheet (SNLS484J).
  - Protection and buses: SLVA680A, TPD6S300A, TPD12S016, SLLA270, SLLA272D, TCAN1042H, SLVA689A.
  - Clocks: SLAA322D, SWRA495L.
  - Power: SNVA803, SLYT682, SLYT614, SLVA773, LM10504.
  - Other datasheets: HD3SS3220, TUSB1046-DCI, TUSB9261, TMDS181, SN75DP159.
- **Microchip:** AN26.2, AN13.10, AN2054, AN826, dsPIC33AK oscillator layout page, PolarFire DDR4 skew pages.
- **Other vendors:** Micron TN-41-13, Qualcomm QRB5165 design guidelines (80-PV086-5P), Pulse "Layout Considerations for Pulse Ethernet Magnetics", Intel/USB-IF DevCon (Heck), Renesas R31AN0080EU0102, Efinix AN063, EMA PCIe design guide, Espressif ESP32/ESP32-S3 HW design guidelines, Raspberry Pi "Hardware design with RP2040", ST AN2867 Rev 15 (ECS mirror), AVR186, ADI AN-139 (mirror), MPS AN065, Rohm 60AN066E Rev.004, EPC "Optimizing PCB Layout with eGaN FETs".
- **Fab capability pages:** JLCPCB (PCB and assembly), PCBWay, OSH Park 2- and 4-layer.
- **Blocked:** st.com, analog.com and intel.com refused direct downloads from this environment, so ST AN5122/AN4879, ADI AN-136/Kueck and Intel AN 766/EMIF tables appear only as snippets or mirrors. NXP documents and Silicon Labs AN0016 were also blocked.

---

## 1. USB 2.0 HS, USB 3.x / USB4, USB Type-C (CC, SBU, orientation, ESD)

### Takeaway
USB 2.0 HS is forgiving. Vendors span 75–105 Ω (Qualcomm) to 90 Ω ±15 % (TI). Intra-pair mismatch limits are ≤50 mil (TI SPRAAR7J, Microchip), ≤150 mil (TI USB-controller datasheets) and ≤2 mm (Qualcomm). The commonest limits are ≤4 vias, no stubs and no AC caps. Maximum length ranges from 4 in (TI's 2013 guide) to 250 mm (Qualcomm) and 12 in (TI's 2023 guide).

SuperSpeed intra-pair skew is where vendors diverge most: 2–2.5 mil (TUSB1046, TUSB9261), 5 mil (SPRAAR7J, Microchip, SLLU149) and 5 ps ≈ 0.7 mm (Qualcomm). There is broad agreement on:
- ≤2 vias per trace.
- 75–265 nF TX AC caps (75–200 nF for Gen1 per Qualcomm). TI controller datasheets use 0.1 µF.
- Cap package ≤0402 (≤0603 absolute), with a pad void in the reference plane.
- Part order at the connector: ESD closest, then CMC, then AC caps.

Insertion-loss budgets (Qualcomm, connector to PHY) are −5.5 dB at 2.5 GHz for Gen1 and −7 dB at 5 GHz for Gen2. USB-C-specific numbers:
- CC traces ≥8 mil (VCONN up to 600 mA).
- CC capacitance in the 200–600 pF cReceiver window.
- Protection parts at the receptacle, with no via between the connector and the TVS pin.
- No passives between the PD controller's CC pin and the receptacle.

### Cited Findings

#### USB 2.0 HS (480 Mb/s)
- **TI SLLA414A (Rev. Jan 2026), USB 2.0 protocol table:** no AC coupling capacitors allowed, no polarity reversal, 90 Ω ±15 % differential, 45 Ω ±15 % single-ended, 5 m max cable — [TI SLLA414A](https://www.ti.com/lit/pdf/slla414) [P]
- **TI SPRAAR7J (Rev. Feb 2023), AM57xx/DRA7xx table:**
  - Total length typ 4000 mil (101.6 mm), **max 12000 mil (304.8 mm)**.
  - Intra-pair skew ≤**50 mil (1.27 mm)**.
  - Zdiff 81–90–99 Ω; Zcm 40.5–45–49.5 Ω.
  - **0 stubs**; **≤4 vias per trace**.
  - Spacing ≥**50 mil** to clock or periodic nets and ≥**30 mil** to other nets.
  - The USB2 rows repeat in the AM335x, KeyStone II, K2G, AM65xx and AM62x tables.
  - Source: [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- **TI SPRAAR7A (Jan 2013, earlier revision of the same document number), "USB 2.0 Board Design and Layout Guidelines":**
  - DP/DM "must be no more than **4 inches**".
  - Match "within **two mils**", measured from the package boundary.
  - SE 45 Ω ±10 %.
  - If a stub is unavoidable, keep it <**200 mil**.
  - No extra components on DP/DM; e.g., one pair cannot be routed to two connectors.
  - Keep the PHY JTAG <6 in.
  - Keep switching regulators away from DP/DM, the crystal and the PHY.
  - The guidance loosened substantially between revisions A and J.
  - Source: [TI SPRAAR7A (E2E China copy)](https://e2echina.ti.com/cfs-file/__key/telligent-evolution-components-attachments/13-106-00-00-00-00-33-10/USB-2.0-Board-Design-and-Layout-Guidelines.pdf) [P]
- **TI USB-controller datasheets:**
  - TUSB9261: HS pair mismatch ≤**150 mil**, 90 Ω ±15 %, minimum vias, top/bottom layer. A CMC, if used, goes as close as possible to the connector pins, with ESD closer still.
  - TUSB7340 (SLLU149E): same 150 mil. If routing longer than **8 in**, "contact TI".
  - Sources: [TI TUSB9261](https://www.ti.com/lit/ds/symlink/tusb9261.pdf) [P]; [TI SLLU149E](https://www.ti.com/lit/pdf/sllu149) [P]
- **Qualcomm QRB5165 design guidelines (80-PV086-5P, Jul 2023), USB 2.0 table:**
  - Zdiff **75–105 Ω**; intralane match **2 mm**; max PCB trace **250 mm**; spacing to other signals **3 × line width**.
  - Keep the 1 kΩ resistor stubs on DP/DM as short as possible.
  - External components near the USB connector.
  - Source: [Qualcomm USB 2.0 routing constraints](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb-2dot0-routing-constraints.html) [P]; [Qualcomm SS/HS-USB guidelines](https://docs.qualcomm.com/doc/80-PV086-5P/topic/SS-USB-and-HS-USB-with-PHY-layout-guidelines.html) [P]
- **Microchip AN26.2 (USB57x4/USB553x hubs):**
  - DP/DM Zdiff 90 Ω **+5/−10 Ω**; Z0 40–55 Ω.
  - HS pair members within **1.25 mm (50 mil)**.
  - "Traces longer than ~15 cm (~6 in) may significantly degrade signal quality."
  - Gap to other signals ≥**3X**, where X = max(trace width, dielectric height). Worked examples: W 8 mil, H 4.3 mil → 24 mil; W 12 mil, H 22 mil → 66 mil.
  - Meanders: amplitude ≤3X, gap ≥5X.
  - Source: [Microchip AN26.2 (DS00001876B)](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) [P]
- **Microchip AN13.10 (USB3300 PHY):**
  - Example 14 mil traces with 7 mil spacing at 13 mil to the reference.
  - A continuous ground plane under DP/DM extending ≥**5× the pair spacing** to each side.
  - Keep parts ≥5× the 7 mil spacing from the lines; do not route pairs under parts.
  - SE range **42–78 Ω** "acceptable" (Zcm 21–39 Ω).
  - Source: [Microchip AN13.10 (DS00002972A)](https://ww1.microchip.com/downloads/en/Appnotes/AN13.10-Application-Note-DS00002972A.pdf) [P]
- **Connector entry (TI SPRAAR7J §3.5):** for a through-hole receptacle, connect HS pairs on the bottom layer so the TH pin is in the path, not a stub. For SMT receptacles, connect on the top layer with no vias — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- **Connector pad stacks (Microchip AN26.2):** remove unused-layer pads and use ≥**0.5 mm** clearance around TH pins on all layers — [Microchip AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) [P]
- **Cable-shield treatment (vendors conflict):**
  - Microchip AN26.2: **330 Ω ∥ 0.1 µF** shield-to-GND at each connector — [Microchip AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) [P]
  - Microchip AN13.10: industry convention is to ground only the host side. A device-only design should AC-couple the housing only — [Microchip AN13.10](https://ww1.microchip.com/downloads/en/Appnotes/AN13.10-Application-Note-DS00002972A.pdf) [P]
  - TI SPRAAR7A:
    - Short the connector shell to a small chassis-ground strap under the connector, but keep signal GND under pins 1–6.
    - Use a ferrite of **10–50 Ω at 100 MHz** in series with the shield, resistive to ~1 GHz.
    - Optionally put a **47–1000 Ω at 100 MHz** ferrite in VBUS near pin 1.
    - Source: [TI SPRAAR7A](https://e2echina.ti.com/cfs-file/__key/telligent-evolution-components-attachments/13-106-00-00-00-00-33-10/USB-2.0-Board-Design-and-Layout-Guidelines.pdf) [P]

#### USB 3.x SuperSpeed / USB4
- **TI SLLA414A, "USB 4.0, 3.2 Gen1/Gen2" table:**
  - Gen1 2.5 GHz (5 Gb/s), Gen2 5 GHz (10 Gb/s), USB4 Gen3 10 GHz (20 Gb/s NRZ), USB4 Gen4 20 GHz (40 Gb/s PAM3).
  - AC caps required on TX, optional on RX. Polarity reversal allowed on SSTX/SSRX.
  - Max intra-pair skew **15 ps/m ("TI recommends 5 mils")**.
  - 90 Ω ±15 % differential / 45 Ω ±15 % single-ended; 3 m cable.
  - Source: [TI SLLA414A](https://www.ti.com/lit/pdf/slla414) [P]
- **Qualcomm USB 3.1/DisplayPort table (connector-to-PHY channel):**
  - Zdiff **70–100 Ω**.
  - Channel IL budget **−7 dB at 5 GHz** (Gen2) and **−5.5 dB at 2.5 GHz** (Gen1).
  - Intralane match **5 ps (700 µm)**; interlane match **70 ps (10 mm)**; DP AUX intralane **50 ps (7 mm)**.
  - Rx-to-Tx spacing 4 × W (Gen2) or 3 × W (Gen1); spacing to other signals 4 × W.
  - AC cap **75–265 nF** (Gen2), **75–200 nF** (Gen1).
  - Further guidance: route pairs on inner layers with solid GND; use ≤**2 core vias** per signal; "TX AC coupling can be anywhere along the line, but better be placed close to source or the ESD/connector side"; isolate from 2.4 GHz antennas.
  - Sources: [Qualcomm USB 3.1/DP routing constraints](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb3dot1-displayport-routing-constraints.html) [P]; [Qualcomm SS/HS-USB guidelines](https://docs.qualcomm.com/doc/80-PV086-5P/topic/SS-USB-and-HS-USB-with-PHY-layout-guidelines.html) [P]
- **Intra-pair skew across vendors (largest spread found):**
  - TUSB1046-DCI: "within **2 mils**" — [TI TUSB1046-DCI](https://www.ti.com/lit/ds/symlink/tusb1046-dci.pdf) [P]
  - TUSB9261: ≤**2.5 mil** — [TI TUSB9261](https://www.ti.com/lit/ds/symlink/tusb9261.pdf) [P]
  - SPRAAR7J tables, Microchip AN26.2 (0.13 mm) and SLLU149E: ≤**5 mil** — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]; [Microchip AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) [P]; [TI SLLU149E](https://www.ti.com/lit/pdf/sllu149) [P]
  - Qualcomm: **5 ps ≈ 0.7 mm (27.5 mil)** — [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb3dot1-displayport-routing-constraints.html) [P]
- **Impedance targets disagree:**
  - TI SLLA414A, TUSB9261, TUSB1046 and SLLU149E: 90 Ω ±15 %.
  - SPRAAR7J AM57xx: 83.7–90–96.3 Ω. SPRAAR7J AM65xx: 95 Ω ±5 %.
  - Microchip AN26.2: **85 Ω ±5 Ω**.
  - Qualcomm: 70–100 Ω, including manufacturing variation.
  - Sources: as above [P]
- **Vias:** ≤**2 per USB3 trace** (SPRAAR7J tables; TUSB1046 "2 or less"; Qualcomm "no more than two core vias"). Microchip AN26.2 adds complementary GND vias when SS changes layers — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]; [TI TUSB1046-DCI](https://www.ti.com/lit/ds/symlink/tusb1046-dci.pdf) [P]; [Microchip AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) [P]
- **Max length, TI:**
  - USB3 SS ≤**3500 mil (88.9 mm)** on AM57xx; ≤5500 mil on KeyStone II; ≤4000 mil on AM65xx.
  - TUSB7340: SS pair "can be no longer than **eight inches**, this is based on the SS USB compliance channel spec".
  - Sources: [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]; [TI SLLU149E](https://www.ti.com/lit/pdf/sllu149) [P]
- **Intel/USB-IF DevCon (Howard Heck, "SuperSpeed USB Design Guidelines"), 5 Gb/s:**
  - Host PCB 2–12 in; device PCB 1–4 in.
  - Channel IL −6 to −20 dB, of which cable −7.5 dB max.
  - Stub reflections "cost up to 1 in of routing per via"; bottom-side connector entry recommended.
  - ESD + CMC "reduces max route length by ~1 in". Use 100 % voids under the CMC and ESD, and 0402 0 Ω no-stuff options for the CMC.
  - Device side: keep trace length ≤2 in.
  - The slide text was partially garbled.
  - Source: [Heck, USB-IF DevCon slides](https://community.infineon.com/gfawx74859/attachments/gfawx74859/usb-superspeed-peripherals/18243/1/2-4_SSUSB_DevCon_DesignGuidelines_Heck.pdf) [P, partially legible]
- **Crosstalk spacing:**
  - TI TUSB9261: **5W** between SS TX/RX pairs and between SS and DP/DM (e.g., 5 mil traces → 25 mil air gap). If impossible, ground-fill between them or route on opposite sides of a GND plane.
  - TI HD3SS3220 and SPRAAR7J: 5W between pairs, a 30 mil keep-out to any other signal and 50 mil to clocks.
  - TUSB1046: pairs separated ≥**3 × W**.
  - Microchip: SS to all other signals ≥**5X** (7 mil → ≥35 mil).
  - Sources: [TI TUSB9261](https://www.ti.com/lit/ds/symlink/tusb9261.pdf) [P]; [TI HD3SS3220](https://www.ti.com/lit/ds/symlink/hd3ss3220.pdf) [P]; [TI TUSB1046-DCI](https://www.ti.com/lit/ds/symlink/tusb1046-dci.pdf) [P]; [Microchip AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) [P]
- **AC-coupling value:**
  - **75–265 nF** total for Gen1/Gen2: TUSB1046 electrical table (its DP receiver max was changed from 200 nF to 265 nF in a revision); Qualcomm for Gen2; TI forum and TMUXHS4212 UG.
  - Qualcomm gives **75–200 nF** for Gen1.
  - TI TUSB9261/TUSB7340 use **0.1 µF**.
  - 220 nF TX (with optional 330 nF RX) is common on Type-C redrivers.
  - Sources: [TI TUSB1046-DCI](https://www.ti.com/lit/ds/symlink/tusb1046-dci.pdf) [P]; [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb3dot1-displayport-routing-constraints.html) [P]; [TI SLLU149E](https://www.ti.com/lit/pdf/sllu149) [P]; [TI E2E TUSB1044](https://e2e.ti.com/support/interface-group/interface/f/interface-forum/724790/tusb1044-about-tx-and-rx-ac-coupling) [S]; [TI SLAU823](https://www.ti.com/document-viewer/lit/html/SLAU823/ac-coupling-capacitors-x1260) [S]
- **AC-cap package and pad treatment:**
  - Maximum **0603** with 0402 "strongly recommended" (SPRAAR7J, SLLA414A). TUSB9261/SLLU149E: "no bigger than **0402**. C-packs are not allowed", placed symmetrically as close as possible to the connector pins. SLLA414A adds 0201.
  - Void the reference plane under SMD pads **100 %, ≥2 layers deep** (SLLA414A). SPRAAR7J's ESD/EMI section says **60 %** voids under ESD/EMI signal pads, while Heck says 100 % under CMC and ESD. Conflict.
  - Sources: [TI SLLA414A §4.10](https://www.ti.com/lit/pdf/slla414) [P]; [TI SPRAAR7J §3.10, §3.14](https://www.ti.com/lit/pdf/spraar7) [P]; [TI TUSB9261](https://www.ti.com/lit/ds/symlink/tusb9261.pdf) [P]
- **In-line part order:**
  - TUSB9261/SLLU149E: ESD clamps "closer than the choke and transmitter capacitors", CMC "closer than the transmitter capacitors".
  - SPRAAR7J: AC caps on the protected side of the CMF, as close as possible to it.
  - Qualcomm: TX caps "close to source or the ESD/connector side".
  - All three are consistent with the order **connector → ESD → CMC → AC cap → PHY**.
  - Sources: [TI TUSB9261](https://www.ti.com/lit/ds/symlink/tusb9261.pdf) [P]; [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]; [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/SS-USB-and-HS-USB-with-PHY-layout-guidelines.html) [P]
- **Cap-to-redriver minimum distance:** TUSB1002A material sets a minimum cap distance of **0.25 in (6.35 mm)** from the redriver — [TI E2E TUSB1002](https://e2e.ti.com/support/interface-group/interface/f/interface-forum/656208/tusb1002-ac-coupling-capacitors-for-usb-3-1-gen-2) [S]
- **Routing details (TUSB1046):**
  - Bends ≥**135°**, with balanced left/right bends.
  - All pairs on the same layer.
  - Test points only in series and symmetric, never as stubs.
  - Source: [TI TUSB1046-DCI §10.1](https://www.ti.com/lit/ds/symlink/tusb1046-dci.pdf) [P]
- **HD3SS3220 stackup note:** route directly adjacent signal layers at a **90° offset** to each other — [TI HD3SS3220 §9.1.1](https://www.ti.com/lit/ds/symlink/hd3ss3220.pdf) [P]
- **USB4 (secondary, low confidence):**
  - Link-partner loss budget said to shrink from 8.5 dB to 5.5 dB at the 10 G rate.
  - A USB 3.2 Gen2 host-to-connector budget of 8.5 dB is said to limit traces to ~5 in.
  - One summary gives USB4 Gen3 85 Ω ±7 %, skew <3 mil and ~60 mm max.
  - Sources: [Microcontroller Tips USB4 FAQ](https://www.microcontrollertips.com/how-to-test-usb4-designs-faq/) [S]; [Altium USB4](https://resources.altium.com/p/usb-4-design-ultra-fast-serial-data-transfer-your-pcb) [S]; [PCBSync](https://pcbsync.com/?p=31209) [S]

#### USB Type-C: CC, SBU, ESD, orientation
- **CC capacitance:** USB PD §5.8.6 sets cReceiver at **200–600 pF** (controller + protection + external cap). TI's TPD6S300A example uses **220 pF 0201** X7R with ±50 % temperature budget — [TI TPD6S300A CC line capacitance](https://www.ti.com/document-viewer/TPD6S300A/datasheet/cc-line-capacitance-t4582032-9) [S]; [TI TPD4S201-Q1](https://www.ti.com/document-viewer/lit/html/SLVSI17/GUID-51D280C8-EB04-44A3-963E-3B88E8A7E749) [S]
- **CC routing width:**
  - CC ≥**8 mil** for VCONN.
  - TPS65988DK minimum widths: CC1/CC2/PP_CABLE 8 mil, VIN_3V3/LDO 6 mil, component GND 10 mil, GPIO 4 mil. Capacitor GND pin 16 mil where possible.
  - VCONN up to **600 mA** with Ra present.
  - Sources: [TI TPS65987D](https://www.ti.com.cn/document-viewer/cn/TPS65987D/datasheet/GUID-5307ED2F-52B0-4A1F-9169-9D21EC2AC8C5) [S]; [TI TPS65988DK](https://ti.com/document-viewer/lit/html/SLVSFN9A/GUID-9DBFBBE2-2864-4C26-8B17-9D1D5E6F561F) [S]; [TI SLVA888C](https://www.ti.com/document-viewer/lit/html/SLVA888C/GUID-00F49BD1-806B-4083-9CBB-C3D4B1A79D6E) [S]
- **CC direct connection:** connect CC **directly** from the PD controller to the receptacle, with no 0 Ω or other passives in between — [TI SLVA888C](https://www.ti.com/document-viewer/lit/html/SLVA888C/GUID-00F49BD1-806B-4083-9CBB-C3D4B1A79D6E) [S]
- **TPD6S300A (CC/SBU/D± protection) layout:**
  - Place the device as close to the connector as possible.
  - Keep unprotected traces away from protected ones.
  - Route USB2 and SBU as straight as possible, with rounded corners of the largest radius.
  - Do not via onto the D1/D2 pins from another layer; via first and continue on the pin's layer.
  - VBIAS 0.1 µF; VPWR bypass close to the pin on solid ground.
  - Source: [TI TPD6S300A §11](https://www.ti.com/lit/ds/symlink/tpd6s300a.pdf) [P]
- **General ESD numbers (TI SLVA680A, Rev. Apr 2022):**
  - For an IEC 61000-4-2 8 kV strike, dI/dt = 30 A / 0.8 ns = **4×10¹⁰ A/s**, so **0.25 nH adds 10 V** at the protected IC.
  - A 90° corner on the strike path develops a ≥7 kV field and arcs for radii below **~2.6 mm** in air. Use curves or ≤45° corners.
  - Use no via between source and TVS (or route connector → TVS first) and no stub.
  - Put a GND via **immediately adjacent** to the TVS GND pin, stitched to an adjacent-layer plane.
  - Source: [TI SLVA680A](https://www.ti.com/lit/pdf/slva680) [P]
- **Orientation mux, AC caps and ESD behind the receptacle:**
  - TUSB1046 layout example: connector → AC caps → redriver for the SS lanes.
  - Vendor blogs differ on whether the CMC precedes the mux.
  - No primary numeric mux-to-receptacle distance was found.
  - Sources: [TI TUSB1046-DCI Fig. 10-1](https://www.ti.com/lit/ds/symlink/tusb1046-dci.pdf) [P]; [BestPCBs USB-C](https://www.bestpcbs.com/blog/2026/08/usb-c-pcb-design/) [S]

#### Rule table: USB
| ID | Rule | Value (default, with conflicts noted) | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| USB2-Z | Diff impedance | 90 Ω ±15 % (81–99 Ω). Qualcomm allows 75–105 Ω; Microchip 90 +5/−10 Ω | SLLA414A, SPRAAR7J, AN26.2, Qualcomm [P] | All USB 2.0 HS | K net class; width and gap from stackup solver; S verify |
| USB2-SKEW | Intra-pair mismatch | default ≤1.27 mm (50 mil). Range in sources: 0.05 mm (SPRAAR7A 2013) to 3.81 mm (TUSB9261) and 2 mm (Qualcomm) | SPRAAR7J/A, AN26.2, TUSB9261, Qualcomm [P] | HS pairs | K: `skew (max 1.27mm)` + `within_diff_pairs` |
| USB2-LEN | Total length | warn >150 mm (Microchip), error >250 mm (Qualcomm) or >304.8 mm (TI). Legacy limit 101.6 mm (SPRAAR7A) | SPRAAR7J/A, AN26.2, Qualcomm [P] | Connector→PHY | K: `length` with `fromTo('J*-*','U*-*')` |
| USB2-VIA | Vias per trace | ≤4 | SPRAAR7J [P] | | K: `via_count (max 4)` |
| USB2-STUB | Stubs / test points | 0 / 0. Legacy: stub <5.08 mm if unavoidable | SPRAAR7J/A [P] | | G: no T-junctions; no TP pads |
| USB2-SP | Spacing to other nets / clocks | ≥0.76 mm / ≥1.27 mm (TI); ≥3·max(W,H) (Microchip); 3W (Qualcomm) | SPRAAR7J, AN26.2, Qualcomm [P] | | K: `clearance` between classes |
| USB2-REF | Ground under pair | continuous; ≥5 × pair spacing each side | AN13.10 [P] | | G: zone coverage of offset polygon |
| USB2-AC | No AC caps, no P/N swap, no branching to two connectors | — | SLLA414A, SPRAAR7A [P] | | M/G |
| USB2-TH | TH receptacle enters on bottom; SMT on top with no vias; ≥0.5 mm clearance around TH pins | — | SPRAAR7J, AN26.2 [P] | | G |
| USB3-Z | SS diff impedance | 90 Ω ±15 % default; Microchip 85 ±5 Ω; AM65xx 95 ±5 %; Qualcomm 70–100 Ω | as cited [P] | 5/10 Gb/s | K + S |
| USB3-SKEW | Intra-pair | default ≤0.127 mm (5 mil); TUSB9261 ≤0.064 mm; TUSB1046 ≤0.05 mm; Qualcomm ≤0.7 mm (5 ps) | as cited [P] | | K: `skew within_diff_pairs` (device override) |
| USB3-IL | Channel loss connector→PHY | Gen1 ≤5.5 dB at 2.5 GHz; Gen2 ≤7 dB at 5 GHz | Qualcomm [P] | | S: Σ length × dB/in + via/cap allowances |
| USB3-VIA | Vias per trace | ≤2; add GND return vias at each transition | SPRAAR7J, TUSB1046, Qualcomm, AN26.2 [P] | | K `via_count (max 2)`; G return-via test |
| USB3-LEN | Max length | device tables 88.9–139.7 mm; ≤203 mm (TUSB7340); device side ≤50.8 mm (Intel); each via ≈ −25 mm; ESD+CMC ≈ −25 mm | SPRAAR7J, SLLU149E, Heck [P] | | K `length`; S |
| USB3-SP | Pair-to-pair, TX↔RX, SS↔DP/DM | ≥5W (TI) / ≥3W (TUSB1046, Qualcomm Gen1) / ≥4W (Qualcomm Gen2) | as cited [P] | | K: `clearance` |
| USB3-ACV | TX AC cap | 75–265 nF (Gen2), 75–200 nF (Gen1); 100 nF or 220 nF typical | Qualcomm, TUSB1046, SLLU149E [P] | | M |
| USB3-ACPKG | Package / pad void | ≤0402 (≤0603 abs), no C-packs; void reference under pads | TUSB9261, SLLA414A, SPRAAR7J [P] | | M; G zone keep-out under pads |
| USB3-ORDER | Chain order | connector → ESD → CMC → AC cap → PHY, all close to the connector | TUSB9261, SPRAAR7J, Qualcomm [P] | | G: path order and distances |
| USB3-BEND | Bend angle | ≥135° | TUSB1046, SLLA414A [P] | | K `track_angle` (KiCad 10) or G |
| USBC-CC | CC trace width | ≥0.2 mm (8 mil) | TPS65987D/88DK [S] | Type-C with VCONN | K: `track_width (min 0.2mm)` |
| USBC-CCC | CC total capacitance | 200–600 pF | USB PD via TI [S] | | M |
| USBC-DIRECT | No series passives on CC | 0 | SLVA888C [S] | TI PD controllers | M/G |
| ESD-PATH | TVS topology | connector→TVS with no via and no stub; GND via adjacent to TVS GND; corners curved or ≤45° | SLVA680A, TPD6S300A, TPD12S016 [P] | All external I/O | G |

### Inferences
- [D] Intra-pair skew numbers convert to time: 5 ps ≈ 0.7 mm (Qualcomm's own conversion) and 5 mil ≈ 0.75–0.9 ps at 6–7 ps/mm, so TI's limit is ~6× tighter than Qualcomm's. The rule pack should carry the device vendor's value, default to TI's 5 mil when the PHY vendor is unknown, and store Qualcomm's 5 ps as the "physics-justified relaxed" option.
- Heck's "1 in per via" and "~1 in per ESD+CMC" (5 Gb/s) and TI SLLU149's "2 in per via" (PCIe Gen2, §2) give a usable cost model for a placer: each via adds ~25–50 mm of equivalent length to a SerDes channel.
- All primary sources agree on the in-line order connector → ESD → CMC → AC cap. Only the AC-cap position relative to the PHY varies, which is a topology-dependent rule (see PCIe below).

### Gaps
- USB-IF primary documents (USB 3.2/USB4 channel budgets, Type-C layout figures) and Intel PDGs were not accessible. No primary USB4 PCB numbers were found.
- No primary numeric rule was found for SBU routing beyond "straight, short, protected", or for the orientation-mux-to-receptacle distance.

---

## 2. PCIe Gen2 / Gen3 / Gen4 / Gen5 (/Gen6)

### Takeaway
Four vendor sources give usable PCIe numbers:
- **TI SNLA426 (Gen3–5 budget table):** total system loss 23.5 / 28 / 36 dB, with 13 / 14 / 16 dB allotted to a 9 in high-loss motherboard trace, plus per-inch loss tables at 8 and 16 GHz.
- **Qualcomm (single board):** −10 dB at 4 GHz and ≤300 mm for Gen3; −6 dB at 2.5 GHz and ≤250 mm for Gen2.
- **TI SLLU149E (Gen2):** ≤20 in on FR4, with each via costing ~2 in.
- **Efinix:** add-in card trace ≤101.6 mm.

Intra-pair skew is ≤5 mil (TI, Efinix) or 5 ps ≈ 0.7 mm (Qualcomm). EMA quotes ±2 mil for Gen4–6. Sources disagree on two points:
- **AC-cap value:** 75–220 nF (TI SNLA426) vs 176–265 nF for Gen3+ (Qualcomm, Efinix and NXP QorIQ data). 220 nF satisfies both.
- **AC-cap placement:** near RX for chip-to-chip (SNLA426); near the TX terminals for same-board links (SLLU149E); on the TX side (Efinix); anywhere, but best near source or receiver (Qualcomm). Near the connector for add-in/edge-finger links is agreed by TI.

Return vias go within 50 mil (TI Gen5) or within 100–200 mil (EMA, TI general), with at least two. Stubs should be <15 mil preferred, with a Gen5 physics limit of ~51–54 mil (TI); EMA notes a 20 mil stub resonates at 8–16 GHz.

### Cited Findings
- **TI SNLA426 (June 2023), loss budget in dB, Gen3 / Gen4 / Gen5:**

  | Item | Gen3 | Gen4 | Gen5 |
  |---|---|---|---|
  | CPU package | 3.5 | 5 | 9.0 |
  | System-board trace ("9-inch trace with high-loss material") | 13 | 14 | 16 |
  | CEM connector | 0.5 | 0.5 | 1.5 |
  | 4-in add-in card | 6.5 | 8.5 | 9.5 |
  | **Total** | **23.5** | **28** | **36** |
  | Crosstalk mitigation | negligible | <2 | 4–5 |
  | Temperature/humidity loss | – | – | 2–3 |

  Eye after EQ: 25 mV / 15±1.5 mV / 15±1.5 mV height, 0.3 UI width — [TI SNLA426](https://www.ti.com/lit/pdf/snla426) [P]
- **TI SNLA426 Table 9-1, 1-inch SDD21 at 8 GHz / 16 GHz:**

  | Material (Dk, Df) | 8 GHz | 16 GHz |
  |---|---|---|
  | Megtron 6 (3.4, 0.002) | 0.189 dB | 0.336 dB |
  | Rogers (3.48, 0.0037) | 0.251 dB | 0.411 dB |
  | GETEK (4.1, 0.011) | 0.548 dB | 1.017 dB |
  | Nelco 4000-6 (4.0, 0.012) | 0.578 dB | 1.078 dB |
  | **FR4 (4.4, 0.014)** | **0.686 dB** | **1.289 dB** |
  | Tetrafunctional FR4 (4.1, 0.022) | 0.961 dB | 1.844 dB |

  Source: [TI SNLA426](https://www.ti.com/lit/pdf/snla426) [P]
- **Qualcomm QRB5165, PCIe routing constraints:**
  - Gen3 8 Gb/s: channel IL **−10 dB at 4 GHz**, bus length **300 mm**.
  - Gen2 5 Gb/s: **−6 dB at 2.5 GHz**, **250 mm**.
  - Differential **70–100 Ω**; intralane **5 ps (0.7 mm)**.
  - Spacing 4 × W to all others; Rx-to-Tx 4 × W (Gen3) or 3 × W (Gen2).
  - AC cap **176–265 nF** (Gen3) and **75–265 nF** (Gen2).
  - No length matching between REFCLK, TX and RX, and no serpentines required. Do not stagger caps. Put any serpentine at the source breakout.
  - Minimize layer transitions on the main route (only at breakout and connectors).
  - TX AC caps "can be anywhere along the line, but better be placed close to source or receiver side".
  - Source: [Qualcomm PCIe layout guidelines](https://docs.qualcomm.com/doc/80-PV086-5P/topic/PCIe%20layout%20guidelines.html) [P]
- **TI SLLU149E (TUSB73x0, PCIe Gen2 5 Gb/s link):**
  - Drivers and receivers designed for a **20-inch maximum** pair on FR4.
  - 100 Ω differential, 50–55 Ω SE.
  - P/N mismatch <**5 mil**, and "trace length differences over all segments are additive and must be less than 5 mils".
  - Series caps **0.1 µF, 0402**. On add-in cards they sit between TX and the connector, **near the connector**. "If both the upstream device and the downstream device reside on the same circuit board, the capacitors are located **near the TXP/TXN terminals**."
  - "Each signal trace via reduces the maximum trace length by approximately **2 inches**", e.g., 6 vias → 8 in.
  - 45° preferred. If the reference plane must change, use bypass caps next to the vias.
  - Source: [TI SLLU149E](https://www.ti.com/lit/pdf/sllu149) [P]
- **Efinix AN063 (PCIe up to Gen4 x4):**
  - AC cap on the TX side, **176–265 nF**, 220 nF conventional, **0201** recommended.
  - Add-in card trace budget ≤**101.6 mm**; intra-pair skew <**0.127 mm**; no inter-pair requirement; spacing ×5 to other signals.
  - TX and RX on different layers. Round bends preferred, 45° acceptable, no right angles.
  - PCIe 4.0 edge fingers: no inner conductor within **0.381 mm** below the edge-card connector; inner planes must not extend >**2 mm** into the edge-finger footprint.
  - Loss at 6.25 GHz: ~0.5 dB/in for Megtron 6 and ~1 dB/in for FR4; max channel IL for RX 25 dB.
  - Source: [Efinix AN063 v1.2](https://www.efinixinc.com/docs/an063-high-speed-transceiver-design-guidelines-v1.2.pdf) [P]
- **EMA PCIe Design Guide Part 1 (Oct 2025; EDA-reseller Q&A, lower authority than silicon vendors):**
  - Typical end-to-end IL budgets at Nyquist: Gen3 <20 dB at 4 GHz; Gen4 <28 dB at 8 GHz; Gen5 <36 dB at 16 GHz; Gen6 <32 dB at 32 GHz (PAM4).
  - Materials: Gen3 Df <0.010; Gen4 <0.005; Gen5 <0.002; standard FR4 (Df ~0.020) only for Gen1/2 or very short Gen3.
  - "Even 12 inches of standard FR4 can exceed the Gen5 loss budget."
  - At least **2 GND stitching vias within 100–200 mil** of each signal via.
  - Intra-pair ±**2 mil**; ≥3 × W between pairs (≥15–20 mil), ≥4 × W for Gen6.
  - Vias: 8–10 mil drill, 18–22 mil pad, 30–35 mil round antipad. A 20 mil stub resonates near 8–16 GHz.
  - Source: [EMA PCIe Design Guide Part 1](https://www.ema-eda.com/wp-content/uploads/2025/10/PCIe-Design-Guide-Part-1.pdf) [P]
- **NXP:** Gen4 PCB trace adds 1–5 ps jitter and 1.0–1.2 dB loss per inch — [NXP AN12864](https://www.nxp.com.cn/docs/en/application-note/AN12864.pdf) [S]
- **Impedance (TI SNLA426):**
  - The spec allows **70–100 Ω**; add-in cards require **85 Ω**. This excludes vias, cap pads, connectors and cables.
  - REFCLK 100 Ω with ≤200 fs RMS RJ.
  - TI SoC tables: 100 Ω ±10 % (AM57xx, KeyStone) and 95 Ω ±5 % (AM65xx).
  - Sources: [TI SNLA426 §10](https://www.ti.com/lit/pdf/snla426) [P]; [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- **Matching (TI SNLA426):**
  - Intra-pair ≤5 mil.
  - Lane-to-lane matching is not required ("typically up to 1 inch of difference"; §13 also says inter-pair "less than 6 inches", an internal inconsistency).
  - SoC tables: RX and TX pair groups ≤550 mil each (AM57xx/KeyStone), or 6 ns RX / 1.5 ns TX (AM65xx).
  - Sources: [TI SNLA426](https://www.ti.com/lit/pdf/snla426) [P]; [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- **Geometry (TI SNLA426):**
  - Serpentine segments ≥max(3W, 3H).
  - ≥max(5W, 5H) from the reference-plane edge; ≥4H from voids; pairs ≥4–5H apart.
  - Stitching vias within **50 mil** of signal vias.
  - Stubs <15 mil, else backdrill; Gen5 quarter-wave maximum ≈**54 mil** (Megtron 6) or **51 mil** (FR4).
  - **10/20/40 mil** drill/pad/antipad; as many GND stitches around the antipad as possible; via-in-pad preferred; non-functional pads removed.
  - Source: [TI SNLA426 §17–24](https://www.ti.com/lit/pdf/snla426) [P]
- **AC caps (TI SNLA426):**
  - Value 75–220 nF, 220 nF typical.
  - Placement: chip-to-chip → **near RX**; chip-to-connector → near the connector/edge finger.
  - Smallest package (the 0201 pad is 12 mil vs a 5–7 mil 85 Ω trace).
  - Pad void 100 %, two layers, larger than the pad.
  - Source: [TI SNLA426 §25–26](https://www.ti.com/lit/pdf/snla426) [P]
- **AC-cap value cross-check:** NXP QorIQ datasheets (quoted on NXP's forum) give Gen2 75–200 nF and Gen3 176–265 nF, consistent with Qualcomm and Efinix — [NXP community thread](https://community.nxp.com/t5/Layerscape/PCIe-AC-coupling-capacitors-values/m-p/741140) [S]
- **Clock-buffer layout (Renesas R31AN0080EU0102 Rev 1.02, Jun 2026):**
  - No components or vias between the two lines of a pair.
  - Use 0402/0201 parts and avoid 0603.
  - Same layer and same via count, placed symmetrically; "1 mm ⇒ 6 ps".
  - GND via next to each signal via at layer changes.
  - Clock-to-other-signal spacing ≥**3 × W** (5 × W optimal).
  - Each decoupling cap gets its own ground via.
  - Source: [Renesas PCIe Buffer-Mux Layout Recommendations](https://www.renesas.com/en/document/apn/pcie-buffer-mux-layout-recommendations?r=1565126) [P]
- **SoC max lengths (TI):** PCIe ≤4700 mil (AM57xx), ≤5500 mil (KeyStone II/K2G) and ≤4000 mil (AM65xx). The tables allow **0 vias** (AM57xx/KeyStone) vs 2 (AM65xx) — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- **Microstrip vs stripline conflict:** SPRAAR7J "does not recommend stripline routing of the high-speed differential signals". SNLA426 and Efinix favor closely coupled stripline or TX/RX on different layers for crosstalk at Gen4–5 — [TI SPRAAR7J §3.2](https://www.ti.com/lit/pdf/spraar7) [P]; [TI SNLA426 §4](https://www.ti.com/lit/pdf/snla426) [P]; [Efinix AN063](https://www.efinixinc.com/docs/an063-high-speed-transceiver-design-guidelines-v1.2.pdf) [P]

#### Rule table: PCIe
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| PCIE-Z | Diff impedance | 85 Ω (CEM/add-in); spec 70–100 Ω; SoC tables 95–100 Ω | SNLA426, Qualcomm, SPRAAR7J [P] | All gens | K + S |
| PCIE-SKEW | Intra-pair | ≤0.127 mm (5 mil), additive over segments; Qualcomm ≤0.7 mm (5 ps); EMA ±0.05 mm | SNLA426, SLLU149E, Efinix, Qualcomm, EMA [P] | | K: `skew within_diff_pairs` (per `fromTo` segment if caps split the pair) |
| PCIE-LANE | Lane-to-lane | not required; SoC limit e.g. ≤13.97 mm | SNLA426, Qualcomm, SPRAAR7J [P] | | Emit only on device demand |
| PCIE-IL | Board channel budget | single board: Gen2 ≤6 dB at 2.5 GHz / 250 mm; Gen3 ≤10 dB at 4 GHz / 300 mm (Qualcomm). Motherboard-to-CEM: 13 / 14 / 16 dB (Gen3/4/5, TI) | Qualcomm, SNLA426 [P] | | S: Σ length × dB/in(f_N) + per-via/cap allowances |
| PCIE-VIACOST | Via length penalty | ≈ −2 in per via (Gen2 FR4) | SLLU149E [P] | | S/G: include in loss/length score |
| PCIE-ADDIN | Add-in card trace | ≤101.6 mm | Efinix, SNLA426 [P] | CEM add-in cards | K `length` |
| PCIE-STUB | Via stub | <0.38 mm preferred; hard max ≈1.3 mm at Gen5; 20 mil already resonates at 8–16 GHz | SNLA426, EMA [P] | | G: stub from stackup per via |
| PCIE-RV | GND return vias at layer change | ≥2 per signal via; within 1.27 mm (Gen5) / 2.5–5.1 mm (general) | SNLA426, EMA, SPRAAR7J [P] | | G |
| PCIE-ACV | AC cap value | Gen1/2: 75–200 (265) nF; Gen3+: 176–265 nF; TI 75–220 nF. Use 220 nF | Qualcomm, Efinix, SNLA426 [P] | TX | M |
| PCIE-ACPOS | AC cap position | add-in/edge finger: near connector; same board: near TX (SLLU149E) or near RX (SNLA426) or either end (Qualcomm). Never mid-line staggered | as cited [P] | | G: cap distance to endpoint pin or connector < threshold; caps of a pair side by side |
| PCIE-ACPAD | Pad void | 100 %, 2 layers, larger than pad | SNLA426 [P] | | G |
| PCIE-EDGE | To reference-plane edge / voids | ≥max(5W, 5H) / ≥4H | SNLA426 [P] | | G |
| PCIE-SP | Pair spacing | ≥4–5H (TI); ≥4W (Qualcomm Gen3); ≥3W (EMA, ≥4W Gen6) | SNLA426, Qualcomm, EMA [P] | | K `clearance` |
| PCIE-FINGER | Edge-finger reference | no inner copper within 0.381 mm below fingers; planes ≤2 mm into finger footprint | Efinix (citing PCIe 4.0 CEM) [P] | Add-in cards | G: zone keep-outs on inner layers under finger polygon |
| PCIE-SERP | Serpentine | segment ≥max(3W, 3H); place at the mismatched (source) end | SNLA426, Qualcomm [P] | | G |

### Inferences
- [D] Max length from budget: L_max ≈ (budget − Σ via/cap/connector allowances) / dB-per-inch(f_Nyquist).
  - Qualcomm's two anchor points imply roughly 0.85 dB/in at 4 GHz (10 dB over 300 mm) and 0.6 dB/in at 2.5 GHz (6 dB over 250 mm), consistent with lossy FR-4 plus vias.
  - TI's FR4 table gives 0.686 dB/in at 8 GHz, so Gen4 with 14 dB allows ≈20 in before vias. With SLLU149E's −2 in per via and TI's 9 in high-loss reference design, the realistic answer is 9–12 in on FR-4 for Gen4 and much less for Gen5.
  - The pack should store budgets and per-material tables, not mm limits.
- The AC-cap placement disagreement reduces to: (a) at a connector, near the connector; (b) on one board, near either end-point (TI SLLU149E near TX, TI SNLA426 near RX, Qualcomm either), never mid-line. A placer should treat "within N mm of TX pins or RX pins" as satisfied by either end.
- 220 nF satisfies every range quoted (TI 75–220, Qualcomm/Efinix/NXP 176–265), so a BOM checker can enforce 176–220 nF as the universally safe Gen3+ window.

### Gaps
- The PCI-SIG Base and CEM specs (C_TX table, CEM/M.2 budgets) were not accessible. M.2-specific budgets were not found.
- No primary per-via dB figure at 8/16 GHz was found; SLLU149E's "2 in per via" is the only quantified via penalty (Gen2).

---

## 3. DDR3 / DDR4 / LPDDR4

### Takeaway
DDR rules are controller-specific and the spread between vendors is large. Primary tables read this session:
- **TI DDR3 (KeyStone, SPRABI1D), in mils:**
  - Fly-by ADDR/CMD/CTRL matched to CK within ±20 mil at each SDRAM; stubs <80 mil.
  - Byte lane ±10 mil; DQS and CK pairs ±1 mil.
  - 39 Ω to VTT at the last SDRAM, within 500 mil.
  - VREF ≥30 mil wide with ≥15 mil spacing.
- **TI DDR4 and LPDDR4 (AM62x, SPRAD06C), in ps per named segment:**
  - DDR4: DQS→DQ ≤2 ps; total CK→ADDR_CTRL ≤4 ps per SDRAM; CK P/N ≤0.4 ps per segment.
  - LPDDR4: CK/CA/DQS/BYTE ≤450 ps; CK P/N ≤0.75 ps; via stub ≤20/40 mil.
- **Microchip PolarFire DDR4 (≤1600 MT/s):** ADDR/CMD↔CK ±100 ps; DQ↔DQS ±25 ps; R_T 30–50 Ω.
- **Micron TN-41-13:** allocate ~1 % of the clock period to matching, which gives ±1 mm (address) and ±0.5 mm (data) at 800 MHz. Assume 6.5 ps/mm inner-layer velocity and up to 20 ps per via.

So DQ-to-DQS tolerances range from 2 ps (TI AM62x) through 3.5 ps (Intel Agilex 5, snippet) and 10 ps (Intel DDR3) to 25 ps (Microchip). The generator must pick the controller vendor's pack. KiCad 10 can check ps-based `length`/`skew` and pad-to-pad `fromTo()` segments natively.

### Cited Findings

#### DDR3 (TI KeyStone, SPRABI1D, Rev. Jul 2022)
- **Impedance:** **50 Ω ±5 %** SE; **100 Ω ±5 %** on DQS and CK pairs — [TI SPRABI1D §6.3](https://www.ti.com/lit/pdf/sprabi1) [P]
- **ADDR/CMD and CTRL fly-by groups:**
  - Same path controller → each SDRAM in sequence → VTT.
  - Each net matched to CK **within ±20 mil (0.51 mm)** to each SDRAM separately.
  - Same via count per matched segment.
  - Stubs **<80 mil (2.03 mm)**, stub skew **±10 mil**.
  - Solid GND (or DVDD15) reference; close layers.
  - Source: [TI SPRABI1D](https://www.ti.com/lit/pdf/sprabi1) [P]
- **Clock fly-by:** CK pairs matched controller → each SDRAM within **±1 mil**; stubs **<40 mil**; AC VTT termination at the end — [TI SPRABI1D](https://www.ti.com/lit/pdf/sprabi1) [P]
- **Data byte lanes:**
  - DQS pairs **±1 mil**; byte nets **±10 mil**.
  - ≤**2 vias**, equal count across the byte.
  - One layer per byte; no mid-point vias.
  - ODT only, no VTT on data. Bit swaps within a byte allowed.
  - Source: [TI SPRABI1D](https://www.ti.com/lit/pdf/sprabi1) [P]
- **Spacing and matching basis:** center-to-center ≥**5 W**, including serpentine. 4 W is allowed but not above 1066 MT/s. All matching uses stripline-equivalent length — [TI SPRABI1D](https://www.ti.com/lit/pdf/sprabi1) [P]
- **Termination:**
  - **39–42 Ω** (39 Ω 1 % preferred) to VTT = VDDQ/2 = 0.75 V, at the **last SDRAM**.
  - Each trace to its termination ≤**500 mil (12.7 mm)**; the resistor's far side goes directly to the VTT rail.
  - 1 % parts.
  - Source: [TI SPRABI1D §6.2](https://www.ti.com/lit/pdf/sprabi1) [P]
- **VREF:**
  - **0.01 µF + 0.1 µF** at each Vref pin plus 0.1 µF at the source.
  - Trace ≥**30 mil (0.76 mm)**, ≥**15 mil (0.38 mm)** from other nets, top layer, shielded with GND.
  - Tolerance ±1 %.
  - Source: [TI SPRABI1D](https://www.ti.com/lit/pdf/sprabi1) [P]
- **VTT supply:** VTT regulator close to the SDRAMs; VTT island on the component side; ≥1 × 0.1 µF per VTT pin plus ≥1 × **10–22 µF** bulk — [TI SPRABI1D](https://www.ti.com/lit/pdf/sprabi1) [P]
- **Write leveling:** limit **2500 ps** (theoretical). DDR3-1333 example: max <2135 ps (or <1385 ps), min >365 ps, assuming 180 ps/in — [TI SPRABI1D §6.3.1.9](https://www.ti.com/lit/pdf/sprabi1) [P]
- **Micron TN-41-13 (Rev. B 08/13, DDR3 point-to-point):**
  - Decide the matching budget as a share of the timing budget. "1 % (±0.5 %) at 800 MHz clock is 6.25 ps … typical flight times for FR4 near **6.5 ps/mm**. So matching to **±1 mm** allocates 1 % of the clock period".
  - Address branches match "within 1 mm within each net".
  - Data (625 ps bit at 800 MHz): 1 % → **±0.5 mm**.
  - Outer-layer propagation is ~**10 %** faster than inner.
  - "To match all traces within 10 ps, traces must be held within a range of 1.5 mm, 60 mils."
  - Keep via counts equal; "a maximum value for delay through a via to consider is **20 ps**".
  - Source: [Micron TN-41-13 (Hackaday mirror)](https://cdn.hackaday.io/files/19354828041536/tn4113_ddr3_point_to_point_design.pdf) [P]
- **Other vendors (snippet level):**
  - Intel DDR3: byte lane ±**10 ps**, and FPGAs cannot reliably deskew >20 ps; ADDR/CMD to CK ±**20 ps** per device.
  - ISSI: ±10 ps ≈ ±50 mil.
  - PCBWay blog: ±25 mil; stubs <200 mil (ideally <100 mil).
  - Sources: [Intel EMIF DDR3](https://www.intel.com/content/www/us/en/docs/programmable/683385/17-0/layout-guidelines-for-ddr3-sdram-interfaces.html) [S]; [ISSI DDR3](https://www.digikey.com/Site/Global/Layouts/DownloadPdf.ashx?pdfUrl=036C264570594B5589E336C3F96AB73F) [S]; [PCBWay DDR3 blog](https://www.pcbway.com/blog/PCB_Design_Layout/DDR3_PCB_Layout_and_Routing_Guide_Topology_Placement_and_Signal_Integrity_Tip_474c261e.html) [S]

#### DDR4
- **TI AM62x/AM62Lx, SPRAD06C (Rev. Mar 2025), Table 2-6, CK and ADDR_CTRL:**
  - A1+A2 (SoC → first SDRAM) ≤**500 ps**, ADDR_CTRL-to-CK skew ≤**3 ps**.
  - A3 (between SDRAMs) ≤**125 ps**, skew ≤3 ps.
  - AS (stub) 5–17 ps, skew 1.3–3 ps.
  - AT (to termination) ≤**75 ps**, skew ≤14 ps.
  - CK P/N skew ≤**0.4 ps** per segment and ≤**0.8 ps** total.
  - Total CK-to-ADDR_CTRL per SDRAM ≤**4 ps**.
  - ≤3 vias per trace; via count difference ≤1.
  - Spacing 4w (to other DDR4) and 3w (within ADDR_CTRL); 2w allowed for ≤500 mil near endpoints.
  - Rcp = Zo ±1 Ω; Rtt = Zo ±5 Ω. Series termination **not allowed**.
  - Source: [TI SPRAD06C](https://www.ti.com/lit/pdf/sprad06) [P]
- **TI SPRAD06C Table 2-7, data group:**
  - BYTE ≤**500 ps**; DQS P/N ≤**0.4 ps**; DQS-to-DQ ≤**2 ps**.
  - ≤2 vias, count difference 0; spacing 4w/3w.
  - Match only within a byte. Cross-byte matching is "neither required nor recommended".
  - Byte swaps allowed; bit swaps within a byte only without CRC.
  - "1 ps can be equated to 5 mils" of stripline-equivalent length.
  - Source: [TI SPRAD06C](https://www.ti.com/lit/pdf/sprad06) [P]
- **TI SPRAD06C VREF and VTT:**
  - VREFCA nominal **20 mil** trace with 0.1 µF near each device pin.
  - VTT as a power sub-plane at the end of the bus, decoupled near the terminators.
  - VTT is optional with one memory device, but CK termination is still required.
  - Source: [TI SPRAD06C §2.11–2.12](https://www.ti.com/lit/pdf/sprad06) [P]
- **Microchip PolarFire / PolarFire SoC DDR4 (≤1600 MT/s on HSIO banks):**
  - ADDR/CMD groups skew-matched to CK within **±100 ps**; DQ/DM to DQS within **±25 ps**. Read training adjusts DQS for the residual DQ/DQS skew.
  - Fly-by ADDR/CMD and CK, terminated at the last device (VDD/2 or VDDI/2).
  - R_T **30–50 Ω**; Z0 typ 50 Ω; Zdiff 100 Ω; ODT 80/120/240 Ω; DQ needs no VTT.
  - Sources: [Microchip PolarFire DDR4 skew matching](https://onlinedocs.microchip.com/oxy/GUID-FF8061A7-7A15-470F-A6F5-E733C24D85F0-en-US-11/GUID-07D00815-AB98-4174-B330-DAD67471AD0C.html) [P]; [PolarFire SoC DDR4 skew matching](https://onlinedocs.microchip.com/oxy/GUID-FF8061A7-7A15-470F-A6F5-E733C24D85F0-en-US-11/GUID-F644A442-EEC8-417D-9325-2349FBFCBD11.html) [P]; [PolarFire DDR4 section 6.3](https://onlinedocs.microchip.com/oxy/GUID-FF8061A7-7A15-470F-A6F5-E733C24D85F0-en-US-11/GUID-BD989947-FFCE-4A0C-8E25-9CE29DB5E64B.html) [P]
- **Intel Agilex 5 DDR4 down-memory:** DQ-to-DQS within a byte ≈±**3.5 ps**, DQS-to-DQS <**1 ps**, with package length included — [Intel Agilex 5 PCB guidelines](https://www.intel.com/content/www/us/en/docs/programmable/821801/current/skew-matching-guidelines-for-ddr4-memory.html) [S]

#### LPDDR4 (TI AM62x, SPRAD06C Tables 3-6/3-7)
- **CK0 and ADDR_CTRL:**
  - Propagation ≤**450 ps** each (assumes Dk ≈3.7–3.9, Df ≈0.002).
  - CK0 P/N ≤**0.75 ps**.
  - ADDR_CTRL relative to CK0 within **±312.5 ps**, measured die pad to DRAM pin including package.
  - ≤3 vias; via stub ≤**20 mil**; via count difference ≤1.
  - Spacing 5w (other LPDDR4 and non-DDR nets), 3w within ADDR_CTRL.
  - Source: [TI SPRAD06C](https://www.ti.com/lit/pdf/sprad06) [P]
- **Data:**
  - DQS and BYTE ≤450 ps.
  - CK0 delay minus DQS delay = **0 to 3 tCK** (CK longer than DQS).
  - DQS P/N ≤**1.5 ps**; DQS-to-BYTE ≤**150 ps** (per-bit deskew); shortest DQ/DM − DQS ≥**−49 ps**.
  - ≤2 vias; via stub ≤**40 mil**; count difference 0.
  - TI: match in the layout tool to **<20 % of each limit**, then confirm by power-aware IBIS simulation across PVT.
  - Source: [TI SPRAD06C](https://www.ti.com/lit/pdf/sprad06) [P]
- **Delay-to-length conversions differ by vendor:**
  - TI SPRAD06C: 1 ps ≈ 5 mil.
  - TI SPRABI1D: 180 ps/in ≈ 5.6 mil/ps [D].
  - Micron: 6.5 ps/mm ≈ 6.1 mil/ps [D].
  - Renesas: 1 mm ≈ 6 ps.
  - NXP forum: 6 mil/ps for package delay.
  - Sources: [TI SPRAD06C](https://www.ti.com/lit/pdf/sprad06) [P]; [Micron TN-41-13](https://cdn.hackaday.io/files/19354828041536/tn4113_ddr3_point_to_point_design.pdf) [P]; [Renesas](https://www.renesas.com/en/document/apn/pcie-buffer-mux-layout-recommendations?r=1565126) [P]; [NXP community](https://community.nxp.com/t5/i-MX-Processors/LPDDR4-tracing-for-imx8mini/m-p/1027287) [S]

#### Rule table: DDR
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| DDR3-FLY | ADDR/CMD/CTRL vs CK per SDRAM | ±0.51 mm (TI); ±1 mm (Micron); ±20 ps (Intel) | SPRABI1D, TN-41-13 [P]; Intel [S] | DDR3 fly-by | K: `skew` with `fromTo('Usoc-*','UdramN-*')` per SDRAM |
| DDR3-STUB | Fly-by stubs | <2.03 mm ADDR/CMD; <1.02 mm CK; stub skew ±0.25 mm | SPRABI1D [P] | | G |
| DDR3-BYTE | Byte lane | DQS ±0.025 mm; DQ/DM ±0.25 mm (TI) / ±0.5 mm (Micron); ≤2 vias equal; one layer; no mid vias | SPRABI1D, TN-41-13 [P] | | K `skew`, `via_count`; G same-layer |
| DDR3-TERM | VTT termination | 39 Ω 1 % at last SDRAM, ≤12.7 mm | SPRABI1D [P] | | G |
| DDR3-VREF | VREF | ≥0.76 mm wide, ≥0.38 mm to others, 0.01 + 0.1 µF at each pin | SPRABI1D [P] | | K `track_width`, `clearance`; G |
| DDR-SP | Spacing (center-to-center) | ≥5W (DDR3 >1066 MT/s); DDR4 4w/3w; LPDDR4 5w/3w; 2w allowed ≤12.7 mm near ends | SPRABI1D, SPRAD06C [P] | | K `clearance` (edge gap = (k−1)·W) |
| DDR4-SEG | Segment delays | A1+A2 ≤500 ps; A3 ≤125 ps; AT ≤75 ps; AS 5–17 ps | SPRAD06C [P] | AM62x DDR4 | K: `length (max …ps)` with `fromTo()` |
| DDR4-SKEW | Skews | TI: CK P/N ≤0.4 ps/seg; CK↔ADDR ≤4 ps; DQS↔DQ ≤2 ps. Microchip: CK↔ADDR ±100 ps; DQS↔DQ ±25 ps | SPRAD06C, PolarFire [P] | vendor-selected | K: `skew (max …ps)` |
| LP4-DLY | Delays | CK/CA/DQS/BYTE ≤450 ps; CK−DQS 0–3 tCK | SPRAD06C [P] | AM62x LPDDR4 | K + S |
| LP4-STUB | Via stub | CA ≤0.51 mm; data ≤1.02 mm | SPRAD06C [P] | | G |
| DDR-VIA | Via delay allowance | ≤20 ps per via (worst case) | TN-41-13 [P] | When via counts differ | G/K time-domain via model |
| DDR-XBYTE | No cross-byte matching | — | SPRAD06C [P] | DDR4/LPDDR4 | Do not emit cross-byte skew rules |
| DDR-DERATE | Layout target | ≤20 % of each ps limit in tool, full limit as max | SPRAD06C [P] | All ps rules | Pack policy |

### Inferences
- A KiCad DDR generator should emit **one `fromTo()` rule per SDRAM per group** plus `within_diff_pairs` skew for CK/DQS. Net-class-wide skew cannot express fly-by matching.
- DQ↔DQS ranges from 2 ps (TI) to 25 ps (Microchip), and ADDR↔CK from 4 ps (TI) to 100 ps (Microchip). The pack must be keyed to the controller vendor and device; the tightest value is the fallback when unknown. Micron's "allocate 1 % of the period" gives a principled default: ±0.5 mm data and ±1 mm address at 800 MHz, scaled linearly with clock period.

### Gaps
- No JEDEC primary document was read. ST AN5122 (STM32MP1 DDR tables) and the NXP i.MX8M hardware guides were blocked (only tables of contents and forum snippets were available). Xilinx UG583 and the Intel EMIF tables were not reachable as primary text.

---

## 4. Ethernet 10/100/1000BASE-T (MDI, magnetics, PHY placement, Bob Smith, RGMII)

### Takeaway
Four primary vendor sources (TI SNLA387, TI AN-1469 and DP83867, Microchip AN2054, Pulse) agree on:
- 100 Ω (±10–15 %) MDI pairs, ≤2 vias per trace, and a void under the magnetics.
- A chassis island bridged by caps, resistors or 1206 pads.
- Bob Smith termination of 75 Ω + 1000 pF (rated ≥2 kV per TI, 3 kV per Microchip).
- Keeping digital signals away: ≥0.3 in (Microchip, Pulse) or ≥30 mil between pairs (TI).

They **conflict** on PHY-to-magnetics distance: Pulse says **≥25 mm** for EMI, Microchip says **<1 in** (max 3 in), and TI says total MDI **<2 in**. Magnetics-to-RJ45 is <1 in everywhere. ESD placement also conflicts: TI's Ethernet note says the PHY side of the magnetics, against the generic connector-side rule. RGMII (DP83867): skew <11 ps (~60 mil); length <2 in recommended, <6 in maximum.

### Cited Findings
- **TI SNLA387 (June 2021):**
  - MDI total **<2 in**; match within pairs **20 mil** (1G) and **50 mil** (10/100); minimal vias and stubs; **100 Ω ±10 %**.
  - MII <6 in, 50 Ω ±10 %. Different pairs ≥**30 mil** apart.
  - Ground void only under in-line parts (magnetics, chokes, AC caps, ESD): 2-layer void for standard designs, all-layer for automotive, void edge ~**20 mil** past the component edge.
  - No metal under the magnetics on any layer (integrated-magnetics RJ45 excepted).
  - Earth ground isolated by ≥**20 mil keep-out on all layers**, bridged by a cap and ≥**1 MΩ**.
  - ESD: the Ethernet-specific TI note puts protection on the **PHY side** of the magnetics, because of common-mode swings on the cable side.
  - Source: [TI SNLA387](https://www.ti.com/lit/pdf/snla387) [P]
- **TI AN-1469 (SNLA079D, PHYTER 10/100):**
  - MDI **50 Ω to ground / 100 Ω differential**. Place the 49.9 Ω 1 % terminations and 0.1 µF near the TD/RD pins.
  - No stubs; ideally no crossover or via.
  - Bob Smith 75 Ω + **1000 pF ≥2 kV** (not applicable to PoE).
  - Do not overlap chassis and circuit planes. Bridge with **two 1206 0 Ω** resistors on either side of the RJ45, replaceable by caps or beads at EMC test.
  - MII/RMII ideally <**6 in**, matched within **2 in**.
  - 25 MHz crystal C_L1 ≈ 2·C_L − 7 pF, i.e. ~3.5 pF stray assumed [D].
  - Source: [TI AN-1469 SNLA079D](https://www.ti.com/lit/pdf/snla079) [P]
- **TI DP83867 datasheet (SNLS484J, Rev. Jun 2026):**
  - RGMII 50 Ω; TXD[3:0] and RXD[3:0] skew **<11 ps (~60 mil FR4)**; length **<2 in recommended, <6 in max**. GMII same lengths.
  - MDI 50 Ω SE / 100 Ω diff, routed to the transformer on the same layer.
  - Void supplies and ground beneath the magnetics; no metal under the transformer.
  - Chassis island bridged by 1206 R and C on either side of the connector.
  - No floating metal and no metal between differential traces. ≥4 layers (6 recommended).
  - Source: [TI DP83867](https://www.ti.com/lit/ds/symlink/dp83867ir.pdf) [P]
- **Microchip AN2054 (Gigabit Ethernet Design Guide):**
  - Intra-pair skew <**50 mil**, inter-pair <**600 mil**; ≤**2 vias** per trace, matched.
  - PHY→magnetics **<1 in** (≤3 in if unavoidable); magnetics→RJ45 **<1 in**; total <**4 in**.
  - Other signals ≥**0.3 in** from pairs; pairs ≥0.3 in apart except near PHY, magnetics and RJ45.
  - Bob Smith 75 Ω + 1000 pF **3 kV** (or 1500 pF/2 kV), with ≥**50 mil** around that cap.
  - Clear planes from halfway through the magnetics to the RJ45 (HV barrier, discrete magnetics only).
  - Chassis island with 2–3 **1206** pads across the void.
  - Bypass pad-to-via <10 mil.
  - Source: [Microchip AN2054](https://ww1.microchip.com/downloads/en/Appnotes/00002054A.pdf) [P]
- **Pulse "Layout Considerations for Pulse Ethernet Magnetics and Ethernet Connector Modules":**
  - Magnetics→RJ45 **<25 mm**.
  - "Isolate the PHY from the Ethernet magnetic; the distance between them needs to be **25 mm (approx. 1 inch) or greater**. Among PHY vendors, this rule is considered good design practice for EMI".
  - Keep the PHY and TX pairs ≥**25 mm** from the PCB edge. A figure suggests LAN silicon traces ≥1 in from the edge (2 in preferred) and LAN silicon **1–4 in** from the connector.
  - TX–RX traces ≥**50 mil** apart (100 mil preferred); pair length match **50 mil (1.25 mm)**; total <**4 in**.
  - No digital signal within **300 mil (7.5 mm)** of the pairs; ≤2 vias per trace.
  - "Route traces away from board edges by a distance greater than the trace height above the ground plane."
  - 100 Ω ±15 %. Pairs closer than 30 mil edge-to-edge lower Zdiff by up to 10 Ω.
  - Source: [Pulse layout considerations (Farnell copy)](https://www.farnell.com/datasheets/2699973.pdf) [P]
- **TI forum on DP83867:** keep PHY→RJ45 ≲**3 in** — [TI E2E DP83867IR](https://e2e.ti.com/support/interface-group/interface/f/interface-forum/774556/dp83867ir-max-distance-between-magnetics-and-phy) [S]

#### Rule table: Ethernet
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| ETH-Z | MDI impedance | 100 Ω ±10 % (TI) / ±15 % (Pulse) | SNLA387, DP83867, Pulse [P] | 10/100/1000BASE-T | K + S |
| ETH-LEN | MDI length | ≤50.8 mm total (TI SNLA387); ≤101.6 mm PHY→RJ45 (Microchip, Pulse) | as cited [P] | | K `length` with `fromTo(PHY, RJ45)` |
| ETH-SKEW | Intra / inter | 0.51 mm (1G) / 1.27 mm (10/100); inter-pair <15.2 mm | SNLA387, AN2054, Pulse [P] | | K |
| ETH-VIA | Vias | ≤2 per trace, matched | AN2054, Pulse [P] | | K `via_count (max 2)` |
| ETH-SP | Pair-to-pair / to digital | ≥0.76 mm (TI) or ≥1.27–2.54 mm TX↔RX (Pulse); digital ≥7.6 mm (Microchip, Pulse) | as cited [P] | | K `clearance` |
| ETH-PLC | PHY↔magnetics | **conflict:** ≥25.4 mm (Pulse, EMI) vs <25.4 mm, max 76.2 mm (Microchip). Magnetics↔RJ45 <25.4 mm (all) | Pulse, AN2054 [P] | Discrete magnetics | G (vendor switch; default: magnetics↔RJ45 hard, PHY↔magnetics soft window 25–76 mm) |
| ETH-EDGE | PHY and pairs from board edge | ≥25.4 mm (Pulse); trace ≥1H from edge | Pulse [P] | | G |
| ETH-VOID | Void under magnetics/chokes/ESD/AC caps | 2 layers (all for automotive), ≈0.51 mm margin; HV barrier mid-magnetics→RJ45 | SNLA387, AN2054, DP83867 [P] | | G zone keep-outs |
| ETH-BOB | Bob Smith | 75 Ω + 1000 pF, ≥2 kV (TI) / 3 kV (Microchip); ≥1.27 mm clearance around cap; not for PoE | AN-1469, AN2054 [P] | Discrete magnetics | M + K clearance |
| ETH-CHAS | Chassis isolation | ≥0.51 mm all layers; bridge = cap + ≥1 MΩ (SNLA387) or 1206 0 Ω/R/C (AN-1469, DP83867) | as cited [P] | Shielded RJ45 | K `clearance` GND↔CHASSIS |
| ETH-ESD | ESD location | PHY side of magnetics (TI Ethernet note) vs connector (generic) | SNLA387 vs SLVA680A [P] | | Vendor switch |
| RGMII-SKEW | RGMII data skew / length | <11 ps (~1.5 mm); <50.8 mm rec., <152 mm max | DP83867 [P] | 1G MAC–PHY | K `skew (max 11ps)`, `length` |

### Inferences
- PHY↔magnetics should be a *soft window* rather than a single bound. Pulse argues for ≥25 mm (EMI isolation) and Microchip for ≤25 mm (≤76 mm hard), so the placer can target ~25 mm and treat >76 mm as an error.
- The ESD location must be a pack parameter (PHY side vs connector side), because TI states both positions in two different notes.

### Gaps
- No IEEE 802.3 primary text on PCB isolation clearance was read.

---

## 5. HDMI, DisplayPort, MIPI CSI-2/DSI (D-PHY), SATA, UFS

### Takeaway
- **HDMI TMDS:** 100 Ω ±15 % with no AC caps. Source skew budget is 0.15 Tbit intra-pair and 0.20 Tcharacter inter-pair (TI). TI SoC tables add ≤4000 mil, 0 vias and ≤5 mil.
- **DisplayPort:** 100 Ω ±10 % with AC caps of 75–200 nF (some TI parts now 75–265 nF) and ≤20 ps intra-pair. Qualcomm adds 5 ps intra-lane, 70 ps inter-lane and 50 ps AUX.
- **MIPI D-PHY:** length and loss trade off with data rate (Qualcomm: 260 mm at 0.5 Gb/s, 150 mm at 2.5 Gb/s with cable). Qualcomm intralane is 0.7 mm and interlane 1.4 mm; TI AM62x lane skew is ≤40 ps.
- **SATA:** 100 Ω ±15 % with 10 nF AC caps (0402, near the connector), skew ≤2.5–5 mil and few or no vias. P/N swap is allowed on some TI controllers.
- **UFS:** Qualcomm 5 ps intralane, 30 ps lane-to-lane, 25–150 mm.

### Cited Findings
- **HDMI (TI SLLA414A):** HDMI 1.4b data to 1.7 GHz, 2.0b to 3 GHz, 2.1b to 6 GHz. **No AC caps**; no polarity reversal. Source intra-pair ≤**0.15 × Tbit**, inter-pair ≤**0.20 × Tcharacter**. **100 Ω ±15 %** — [TI SLLA414A](https://www.ti.com/lit/pdf/slla414) [P]
- **HDMI (TI SPRAAR7J AM57xx):** TMDS 90–110 Ω; ≤**4000 mil**; ≤5 mil intra-pair; **0 vias** — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- **HDMI retimer/repeater datasheets (TI TMDS181, SN75DP159):**
  - TMDS on the top layer to avoid vias, with matched electrical length for inter- and intra-pair skew.
  - Solid GND next to the signal layer; **L1–L2 5–10 mil** in the recommended 4/6-layer stack.
  - Control signals on the bottom.
  - Sources: [TI TMDS181](https://www.ti.com/lit/ds/symlink/tmds181.pdf) [P]; [TI SN75DP159](https://www.ti.com/lit/ds/symlink/sn75dp159.pdf) [P]
- **HDMI ESD (TI TPD12S016):**
  - As close to the connector as possible.
  - Keep unprotected traces away from protected ones.
  - **No vias between the connector and the protection pins**; no 90° turns; minimal GND-path impedance.
  - Source: [TI TPD12S016 §10.1](https://www.ti.com/lit/ds/symlink/tpd12s016.pdf) [P]
- **HDMI inter-channel matching:** ADI ADV3003 keeps the four channels within **0.05 in** on FR4. Intel HDMI tips: 100 Ω ±10 %, ≤2 vias — [ADV3003 datasheet mirror](https://www.alldatasheet.net/html-pdf/1075459/AD/ADV3003/435/13/ADV3003.html) [S]; [Intel AN 837](https://www.intel.com/content/www/us/en/docs/programmable/683677/current/ip-board-design-tips.html) [S]
- **DisplayPort (TI SLLA414A):** AC caps required; source intra-pair ≤**20 ps** (≈5 mil); **100 Ω ±10 %** — [TI SLLA414A](https://www.ti.com/lit/pdf/slla414) [P]
- **DisplayPort (Qualcomm USB 3.1/DP table, applies to DP lanes):**
  - Intralane **5 ps (0.7 mm)**; interlane **70 ps (10 mm)**; AUX intralane **50 ps (7 mm)**.
  - Caps 75–265 nF (10 Gb/s) / 75–200 nF (5 Gb/s).
  - Source: [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb3dot1-displayport-routing-constraints.html) [P]
- **DP AC-cap value:**
  - TI TUSB1046-DCI changed its DP receiver AC-cap maximum to **265 nF from 200 nF** in a revision. Its electrical table lists C_AC 75–265 nF — [TI TUSB1046-DCI](https://www.ti.com/lit/ds/symlink/tusb1046-dci.pdf) [P]
  - Older TI and Diodes material cites DP 1.2 **75–200 nF** on ML and AUX — [TI SN75DP126](https://www.ti.com/document-viewer/ja-jp/SN75DP126/datasheet/application_and_implementation) [S]; [Diodes AN341](https://www.diodes.com/assets/Part-Support-Files/PI3VDP12412/AN341.doc) [S]
- **MIPI CSI D-PHY (Qualcomm, up to 2.5 Gb/s/lane), max PCB trace vs data rate:**

  | Data rate (Gb/s/lane) | 0.5 | 0.75 | 1.0 | 1.5 | 2.1 | 2.5 |
  |---|---|---|---|---|---|---|
  | Total channel IL | −2.1 dB | −2.3 dB | −2.3 dB | −2.5 dB | −3.5 dB | −6.5 dB |
  | Max trace, better cable (e.g. 0.5 Gb/s with cable IL ≥ −0.5 dB) | 260 mm | 210 mm | 200 mm | 145 mm | 170 mm | 210 mm |
  | Max trace, worse cable (cable IL −0.5 to −1.0 dB) | 190 mm | 155 mm | 125 mm | 60 mm | 90 mm | 150 mm |

  - The table pairs each rate with an example flex-cable length (3 in or 6 in), which explains why the limits are not monotonic in rate.
  - Diff 70–100 Ω, SE 36–52 Ω ("relaxed from the legacy 100/50 Ω").
  - Intralane **0.7 mm**, interlane **1.4 mm**.
  - Spacing to other signals 2.5 × W; intralane spacing 1 × W; interlane spacing 1–1.5 × W.
  - Source: [Qualcomm MIPI CSI D-PHY routing](https://docs.qualcomm.com/doc/80-PV086-5P/topic/mipi-csi-d-phy-routing-constraints-up-to-2dot5-Gbps.html) [P]
- **MIPI CSI (TI SPRAAR7J AM62x):**
  - CSI ≤**10 in**; 85–115 Ω; SE 50 Ω; pairs "loosely coupled" (LP mode).
  - Intra-pair skew via the mode-conversion S-parameter limits; estimate **UI/50**, i.e. 8 ps at 1.25 GHz [D].
  - Lane skew ≤**40 ps** (0.1 UI); ≤2 vias.
  - Source: [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- **SATA (TI TUSB9261):**
  - **100 Ω ±15 %**; mismatch ≤**2.5 mil**.
  - Inline caps ≤**0402**, no C-packs, symmetric and close to the SATA connector.
  - TX↔RX 5W.
  - "It is permissible to swap the plus and minus on the SATA differential pair", but not TX with RX.
  - Source: [TI TUSB9261](https://www.ti.com/lit/ds/symlink/tusb9261.pdf) [P]
- **SATA (TI SPRAAR7J):** 85–115 Ω; ≤**3500 mil** (AM57xx) or ≤**5500 mil** (KeyStone II); ≤5 mil; **0 vias** — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- **SATA cap values and polarity, other sources:**
  - TI TDA2 datasheet: caps **0.3–12 nF, typ 10 nF**, on TX and RX — [TI TDA2E](https://www.ti.com/document-viewer/TDA2E/datasheet/sata-interface-schematic-sprabp6-c001) [S]
  - LattePanda: no polarity inversion; caps within ~10 mm of the connector — [LattePanda](https://docs.lattepanda.com/content/mu_edition/design_guide_sata/) [S]
  - The polarity rule conflicts with TUSB9261 and is controller-dependent.
- **UFS (Qualcomm):**
  - Gear 3 6 Gb/s: −6 dB at 3 GHz, bus 25/75/150 mm, 75–105 Ω.
  - Gear 4 10 Gb/s: −1.3 dB at 2.9 GHz and −5.0 dB at 5.8 GHz, ≤70 mm, 70–110 Ω.
  - Intralane **5 ps (0.7 mm)**; TX1↔TX2 or RX1↔RX2 **30 ps (4.2 mm)**.
  - Rx-to-Tx spacing 1.5–3 × W; others 2–3 × W.
  - Source: [Qualcomm UFS routing](https://docs.qualcomm.com/doc/80-PV086-5P/topic/UFS%20routing%20constraints.html) [P]

#### Rule table: video, camera, storage
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| HDMI-Z | TMDS impedance | 100 Ω ±15 % (TI SoC ±10 %) | SLLA414A, SPRAAR7J [P] | HDMI 1.4–2.1 | K + S |
| HDMI-SKEW | Intra / inter | ≤0.15 Tbit / ≤0.20 Tchar (6 Gb/s → 25 ps [D]); TI SoC ≤5 mil; ADI inter-channel ≤1.27 mm | SLLA414A, SPRAAR7J [P]; ADV3003 [S] | | K time-domain `skew` |
| HDMI-AC | No AC caps | — | SLLA414A [P] | | M |
| HDMI-VIA | Vias | 0 (TI SoC); top layer (TI retimers); ≤2 (Intel) | SPRAAR7J, TMDS181 [P]; Intel [S] | | K `via_count` |
| HDMI-ESD | ESD | at connector, no vias connector→TVS | TPD12S016 [P] | | G |
| DP-ACV | AC caps | 75–200 nF (DP 1.2 practice) or 75–265 nF (newer TI, Qualcomm 10 Gb/s); 0402 | as cited | DP source | M |
| DP-SKEW | Intra / inter / AUX | ≤20 ps (TI) or 5 ps (Qualcomm) / 70 ps / 50 ps | SLLA414A, Qualcomm [P] | | K |
| CSI-LEN | Length vs rate | per Qualcomm table (60–260 mm) or ≤254 mm (TI AM62x) | Qualcomm, SPRAAR7J [P] | D-PHY ≤2.5 Gb/s | K `length`; S with cable IL |
| CSI-SKEW | Intra / inter | 0.7 mm / 1.4 mm (Qualcomm); lane ≤40 ps (TI) | Qualcomm, SPRAAR7J [P] | | K |
| CSI-COUP | Coupling | loose (TI); intralane gap ≥1 × W (Qualcomm) | SPRAAR7J, Qualcomm [P] | | Pack flag |
| SATA-ACV | AC caps | 10 nF (0.3–12 nF) TX and RX; ≤0402 near connector | TUSB9261 [P]; TDA2 [S] | | M + G |
| SATA-SKEW | Intra-pair / vias | ≤0.064–0.127 mm / 0 (TI SoC) | TUSB9261, SPRAAR7J [P] | | K |
| UFS-SKEW | Intra / lane-lane | 0.7 mm / 4.2 mm | Qualcomm [P] | UFS G3/G4 | K |

### Inferences
- UI-based skew budgets (HDMI, D-PHY) should be stored as formulas and resolved to ps at the configured data rate, then to mm with KiCad 10's per-layer delay.
- Qualcomm's MIPI table shows that "max length" depends on the external flex-cable loss. The pack must accept a `cable_il_db` parameter instead of a single length.

### Gaps
- HDMI Forum, VESA and MIPI Alliance primary layout documents were not accessible. No HDMI 2.1 FRL PCB budget was found.

---

## 6. CAN, RS-485, I2C, SD/SDIO and SPI bus limits

### Takeaway
These buses are dominated by cable and bus-level numbers, but several are locally checkable:
- **Termination:** 120 Ω only at the two physical bus ends, or a split 2 × 60 Ω + 4.7 nF for CAN. Protection and filter parts go at the connector, in the signal path.
- **Stub limits:** set by driver transition time. CAN: ≤1/3 of critical length, ISO 0.3 m at 1 Mb/s. RS-485: electrical length <1/10 of rise time.
- **I2C:** rise time and capacitance limits of 1000/300/120 ns and 400/400/550 pF bound the pull-up value.
- **SD/SDIO:** clock-to-data matching 6 mm at 50 MHz and 2 mm at 208 MHz, bus <150 mm and <50 mm respectively, CLK series R 18–27 Ω (Qualcomm). Espressif: SDIO data within ±50 mil of CLK, total ≤2000 mil.

### Cited Findings
- **CAN (TI SLLA270):**
  - ISO 11898: 40 m at 1 Mb/s, ≤**30 nodes**, unterminated stub ≤**0.3 m** at 1 Mb/s.
  - 120 Ω cable, terminated at both ends with 120 Ω; avoid putting the termination inside a removable node.
  - Cable length vs rate: 40 m/1 Mb/s, 100 m/0.5, 200 m/0.25, 500 m/0.10, 1000 m/0.05. Above 100 m: rate (Mb/s) × length (m) ≤ **50**.
  - Split termination: **~60 Ω ±1 %** × 2 with typ **4.7 nF** (3 dB at 1.1 Mb/s).
  - Stub ≤**1/3 critical length**: a 50 ns edge on a 5 ns/m line gives 5 m critical length and a **1.67 m** stub; slope control at 160 ns gives ~5.3 m.
  - Source: [TI SLLA270](https://www.ti.com/lit/pdf/slla270) [P]
- **CAN (TI TCAN1042H, SLLSES7D):**
  - Protection and filtering as close to the bus connector as possible. Use a bidirectional TVS or varistor; optional bus filter caps and CMC go between transceiver and connector.
  - Design protection "in the direction of the signal path. Do not force the transient current to divert from the signal path".
  - ≥**2 vias** for VCC/GND of bypass caps and protection devices.
  - On-board termination must not disappear if a node is removed.
  - Datasheet test conditions use Rterm 60 Ω and Csplit 4.7 nF.
  - Source: [TI TCAN1042H §12.1](https://www.ti.com/lit/ds/symlink/tcan1042h.pdf) [P]
- **RS-485 (TI SLLA272D, Rev. May 2021):**
  - 120 Ω at each cable end, or 2 × 60 Ω low-pass in noisy environments.
  - Stub electrical length < **1/10 of driver 10/90 rise time**: L ≤ t_r · v · c / 10. Examples at 78 % velocity: 1 Mb/s/100 ns → **7 ft**; 250 kb/s/250 ns → 19 ft; 200 kb/s/500 ns → 38 ft.
  - Failsafe bias **2 × 523 Ω** with 120 Ω terminations at 5 V ±5 %; 32 UL, with failsafe biasing worth up to 20 UL.
  - Length (m) × rate (b/s) < **10⁷**.
  - PCB: keep both lines close and equidistant.
  - Source: [TI SLLA272D](https://www.ti.com/lit/pdf/slla272) [P]
- **I2C (TI SLVA689A, Rev. Oct 2026):**
  - t_r max **1000 / 300 / 120 ns** and C_b max **400 / 400 / 550 pF** (Sm / Fm / Fm+); VOL ≤0.4 V at 3 mA.
  - R_P(min) = (VCC − VOL)/IOL; R_P(max) = t_r/(0.8473·C_b).
  - Source: [TI SLVA689A](https://www.ti.com/lit/pdf/slva689) [P]
- **SD card (Qualcomm SDC2):**
  - 50 MHz DDR/100 MHz SDR: card load 10 pF, bus <**150 mm**, clock-to-data **6 mm**.
  - 208 MHz (SDR104): 5 pF, bus <**50 mm**, clock-to-data **2 mm**.
  - Spacing 1.5 × W; CLK series termination **18–27 Ω**.
  - Source: [Qualcomm SDC2 routing](https://docs.qualcomm.com/doc/80-PV086-5P/topic/SDC2%20external%20SD%20card%20routing%20constraints.html) [P]
- **SDIO (Espressif ESP32-S3):** CMD/DATA0–3 within **±50 mil** of SDIO_CLK; total ideally within **2000 mil**; CLK surrounded by ground — [Espressif ESP32-S3 PCB layout](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html) [P]
- **Multi-drop slow clock (Qualcomm SLEEP_CLK):** star branches differ by <**30 mm**; daisy-chain stubs <**7 mm** — [Qualcomm CXO and SLEEP_CLK routing](https://docs.qualcomm.com/doc/80-PV086-5P/topic/CXO-and-SLEEP_CLK-routing.html) [P]
- **SPI/QSPI:** earlier Infineon numbers stand (±30/±200/±1500 mil at 133 MHz) — [rules_highspeed_emi.md §4](./rules_highspeed_emi.md); [Infineon AN240090](https://www.infineon.com/assets/row/public/documents/10/42/infineon-an240090-design-and-layout-guide-for-cyrs17b-cyel17b-flash-quad-devices-applicationnotes-en.pdf)

#### Rule table: field buses and low-speed
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| CAN-TERM | Termination | 120 Ω at the 2 ends only, or 2 × 60 Ω ±1 % + 4.7 nF | SLLA270, TCAN1042H [P] | HS-CAN | M: node role |
| CAN-PROT | TVS/filter/CMC at connector, in the signal path; ≥2 vias on protection GND | — | TCAN1042H [P] | | G |
| CAN-STUB | Stub | ≤0.3 m at 1 Mb/s; ≤1/3 critical length | SLLA270 [P] | | Calc; G daisy-chain T |
| 485-STUB | Stub | <t_r·v·c/10 | SLLA272D [P] | | Calc + K `length` |
| 485-FS | Failsafe bias | 2 × 523 Ω (5 V) | SLLA272D [P] | One node | M |
| I2C-RC | Pull-up range | [(VCC−0.4)/3 mA, t_r/(0.8473·C_b)] | SLVA689A [P] | | M + G (C_b from trace pF/mm + pins) |
| I2C-CB | Bus capacitance | ≤400 pF (Sm/Fm), ≤550 pF (Fm+) | SLVA689A [P] | | G/M |
| SD-MATCH | CLK↔DATA/CMD | ≤6 mm (50 MHz) / ≤2 mm (208 MHz); ±1.27 mm (Espressif SDIO) | Qualcomm, Espressif [P] | SD/SDIO/eMMC | K `skew` |
| SD-LEN | Bus length | <150 mm / <50 mm; ≤50.8 mm (Espressif) | Qualcomm, Espressif [P] | | K `length` |
| SD-RS | CLK series R at source | 18–27 Ω | Qualcomm [P] | | M + G (R near driver) |
| CLK-STAR | Slow multi-drop clock | branch Δ <30 mm; daisy stub <7 mm | Qualcomm [P] | | G |

### Inferences
- On a PCB the CAN and RS-485 stub limits only matter for daisy-chained connectors. The useful on-board checks are "termination present only on end nodes" and "protection in the signal path at the connector".
- The I2C pull-up and capacitance check can be fully automated from stackup capacitance per mm, and it catches a common real-world failure.

### Gaps
- No primary numeric TVS-to-connector distance was found for CAN or RS-485. NXP UM10204 (the I2C spec) was blocked; the I2C numbers are TI's restatement.

---

## 7. Clocks and crystals

### Takeaway
Primary numeric placement rules found:
- **Upper bound:** Microchip dsPIC33AK keeps the oscillator circuit ≤12 mm (½ in) from the pins, on the same side, with load caps next to the crystal.
- **Lower bound:** Espressif keeps the crystal ≥2.7 mm (ESP32) or ≥2.0 mm (ESP32-S3) from the chip's clock pin, to avoid coupling into the chip.
- **Parasitic budgets:**
  - AVR186 typicals: XIN–GND 1 pF, XOUT–GND 2 pF, XIN–XOUT 0.5 pF.
  - Microchip AN826: stray 2–5 pF.
  - TI TUSB9261: C_SHUNT 4.5 pF.
  - TI AN-1469 implies ~3.5 pF.
- **Frequency sensitivity:** ST AN2867 example, 0.175 pF × 45 ppm/pF ≈ 7.8 ppm.

Vendors conflict on:
- **Metal-can grounding:** ST says do not tie it to oscillator ground; TI and AVR say connect the housing to ground.
- **Oscillator ground:** TUSB9261 says VSSOSC must not connect to the board ground plane; most others tie a guard to MCU ground.
- **Copper under the crystal:** most call for solid ground; TI CDCE925 says cut planes. Espressif calls for a top-layer keep-out ring if ground is sufficient.

No primary source gives a numeric distance from switching nodes; all say "away", and Espressif says no magnetic components nearby.

### Cited Findings
- **Microchip dsPIC33AK512MPS512 data sheet, "External Oscillator Layout Guidance":**
  - Same side as the device; "not exceeding **one-half inch (12 mm)**"; load caps next to the oscillator on the same side.
  - A grounded pour around the circuit, routed directly to MCU ground, with no signal or power traces inside.
  - On 2-sided boards no traces on the other side under the crystal.
  - Tie broken guard sections to a mirrored ground layer.
  - Source: [Microchip dsPIC33AK oscillator layout](https://onlinedocs.microchip.com/oxy/GUID-E48B4A26-F201-4F0A-BCBA-16461582816A-en-US-4/GUID-AA04B64F-3C38-4E1C-8B51-49DE3CFE2419.html) [P]
- **Espressif ESP32 and ESP32-S3 HW design guidelines:**
  - "The crystal should be placed far from the clock pin to avoid interference on the chip. The gap should be at least **2.7 mm**" (ESP32) / "at least **2.0 mm**" (ESP32-S3). Add dense ground vias around the clock trace.
  - Series components near the chip; load caps on the two sides of the crystal, not connected directly to the series parts.
  - No signal traces under the crystal; power-trace vias far from the clock trace; ground copper on both sides.
  - "Do not place any magnetic components nearby."
  - A top-layer keep-out around the crystal when top-layer ground is sufficient.
  - A complete GND plane under RF, crystal and chip.
  - Sources: [Espressif ESP32 PCB layout](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html) [P]; [Espressif ESP32-S3 PCB layout](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html) [P]
- **AVR186 (Atmel/Microchip):**
  - Typical parasitics **XIN–GND 1 pF, XOUT–GND 2 pF, XIN–XOUT 0.5 pF**; keep them minimal.
  - Route XIN and XOUT apart; place the XIN cap first and closest; NPO/C0G caps.
  - Ground area under the crystal tied to oscillator ground; housing to ground.
  - Guard ring on single-layer boards.
  - Keep cap grounds clear of USB, RS-232, LIN, PWM and power return currents.
  - Source: [AVR186](https://www.insidegadgets.com/wp-content/uploads/2013/02/Best-Practices-for-the-PCB-layout-of-oscillators.pdf) [P]
- **TI SLAA322D (MSP430 32 kHz):**
  - Shortest traces, with trace capacitance included in C_L; XIN and XOUT apart.
  - Short, symmetric crystal→CL1→CL2 loop with cap grounds close together; never route the ground between the caps or around the crystal.
  - Clean guard ring tied to AVSS only.
  - On 2-layer boards no digital lines under the crystal; fill with clean ground.
  - Housing to ground.
  - Source: [TI SLAA322D](https://www.ti.com/lit/pdf/slaa322) [P]
- **TI SWRA495L (CC13xx/26xx/23xx/27xx, Rev. Apr 2025):**
  - Crystal as close as possible; solid ground plane under the crystal; no high-speed digital nearby.
  - Example: ~2–3 pF internal + 7 pF external → C_L 9 pF.
  - 802.15.4 carrier tolerance ±40 ppm.
  - Source: [TI SWRA495L](https://www.ti.com/lit/pdf/swra495) [P]
- **ST AN2867 Rev 15 (Oct 2021) §7.1:**
  - Crystal as close as possible; grounded guard ring "essential".
  - Dedicated oscillator ground plane connected to the nearest MCU ground.
  - **A metal-can crystal should not be connected to the oscillator ground.**
  - Avoid test points; coat the board in humid environments.
  - No numeric distances.
  - Frequency example: 0.175 pF shift × 45 ppm/pF → **~7.8 ppm**. For LSE choose C_L ≥6 pF (7 pF compromise).
  - Source: [ST AN2867 Rev 15 (ECS mirror)](https://ecsxtal.com/store/pdf/stm32-microcontroller-application-note-092823.pdf) [P]
- **Microchip AN826:** stray capacitance "in the range of 2 to 5 pF"; minimize by keeping traces short — [Microchip AN826](https://ww1.microchip.com/downloads/en/AppNotes/00826a.pdf) [P]
- **TI TUSB9261:** "VSSOSC should not be connected to the PCB ground plane"; C_SHUNT (crystal + board stray) 4.5 pF; 20 pF load — [TI TUSB9261](https://www.ti.com/lit/ds/symlink/tusb9261.pdf) [P]
- **TI AN-1469 (PHYTER):** C_L1 ≈ 2·C_L(spec) − 7 pF; start at 33 pF if unknown — [TI SNLA079D](https://www.ti.com/lit/pdf/snla079) [P]
- **TI CDCE925 (conflict on copper under the crystal):** cut ground and power planes under the crystal — [TI CDCE925](https://www.ti.com/document-viewer/lit/html/SCAS847J/GUID-3FD01874-CDCB-4457-A26C-73DAE96B48CB) [S]
- **Qualcomm CXO:** clock vias "completely surrounded"; a C-shaped ring of GND vias for all clock and RF transitions — [Qualcomm CXO routing](https://docs.qualcomm.com/doc/80-PV086-5P/topic/CXO-and-SLEEP_CLK-routing.html) [P]
- **High-speed separation:** do not route high-speed traces under or near crystals, oscillators, switching regulators or magnetics (no number) — [TI SPRAAR7J §3.2](https://www.ti.com/lit/pdf/spraar7) [P]

#### Rule table: crystals
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| XTAL-DMAX | Crystal + caps to osc pins (upper bound) | ≤12 mm | Microchip DS [P] | MCU Pierce | G |
| XTAL-DMIN | Crystal body to chip clock pin (lower bound) | ≥2.7 mm (ESP32), ≥2.0 mm (ESP32-S3) | Espressif [P] | Espressif SoCs (vendor-specific) | G |
| XTAL-SIDE | Same side as MCU | — | Microchip DS [P] | | G |
| XTAL-CAP | Caps adjacent, XIN cap first, C0G; cap grounds together | — | AVR186, SLAA322D, Espressif [P] | | G + M |
| XTAL-PAR | Parasitic budget | XIN 1 pF, XOUT 2 pF, XIN–XOUT 0.5 pF (typical); total stray 2–5 pF | AVR186, AN826 [P] | | G: trace C from length and stackup |
| XTAL-SEP | XIN/XOUT apart | — | AVR186, SLAA322D [P] | | G |
| XTAL-GUARD | Guard ring/pour, no foreign nets inside or under on adjacent layer; ground-via stitching | — | AN2867, Microchip, SLAA322D, Espressif [P] | | K rule area `disallow`; G |
| XTAL-SER | Series R near chip side | — | Espressif [P] | | G |
| XTAL-MAG | No magnetics nearby | no number | Espressif [P] | | G (heuristic radius) |
| XTAL-CAN | Metal can grounding | ST: no (osc GND); TI/AVR: yes; TUSB9261: VSSOSC isolated from plane | as cited [P] | | Vendor switch |
| XTAL-TP | Avoid test points | — | AN2867 [P] | | G |

### Inferences
- A crystal rule pack needs both a maximum distance (Microchip) and an optional vendor-specific minimum (Espressif), and the optimizer should place within that annulus.
- Parasitic budgets (1–5 pF) give a physical score: trace C = length × C′(stackup). For a 32 kHz LSE at 7 pF C_L, ST's pullability example shows each 0.1 pF matters at the ppm level.

### Gaps
- Silicon Labs AN0016 and Abracon notes were blocked. No primary numeric clearance from switch nodes or inductors to crystal nets was found.

---

## 8. Switching regulators: numeric loop, Cin, switch-node and feedback guidance

### Takeaway
At least one vendor does state a numeric Cin distance. MPS (AN065, NB67x) says "strongly recommended to place the input cap **<2 mm** distance from the chip", with the VCC cap also <2 mm. Rohm says shortening Cbypass wiring "even by 1 mm is highly recommended", that the bulk Cin may sit ~2 cm from the bypass cap, and that Cin and Cout grounds should be 1–2 cm apart.

Loop physics anchors:
- **TI SNVA803:** lateral loop ~20 mm² → >1 nH; vertical loop 2 mm² → <0.5 nH, with 4 V less overshoot.
- **EPC:** 0.4 → 2.9 nH costs >4 % efficiency; overshoot is 100 % of Vin at 1.6 nH vs 30 % at 0.4 nH.
- **TI SLYT682:** 5 A/ns × 2 nH = 10 V.
- **ADI AN-139:** a next-layer plane gives >3× less inductance than a 1.6 mm 2-layer board.

Practical rules:
- 1 via per amp (TI); 10 mil drill / 20 mil pad vias near IN/GND and >20 vias between input caps (MPS).
- SW copper limited to the inductor pad plus the connection; SW trace ≤100 mil wide (TI LM10504).
- No copper under the inductor on the top layer.
- Power trace width >1 mm/A on 1 oz and >0.7 mm/A on 2 oz (Rohm).
- FB divider next to the FB pin with no vias to FB (MPS), sense trace away from SW, inductor and diode, not under them and not parallel to power lines (Rohm, TI).

No numeric SW-to-sensitive-net clearance was found in any vendor document.

### Cited Findings
- **MPS AN065 ("PCB Layout Design Guidelines for NB67x Series"):**
  - "It is strongly recommended to place the input cap **<2mm distance from the Chip**." VCC cap "<2mm distance from the Chip", on the same layer (no via).
  - AGND–PGND single connection close to the VCC cap with ≥2 vias. ≥4 vias VCC cap→AGND and 8 vias cap→PGND (NB675).
  - VIN and PGND on ≥2 layers with vias of **10 mil drill / 20 mil copper**; 1–2 vias each under VIN and PGND pins (NB670/1), ≥3 (NB675); **>20 vias** between the two input caps.
  - Feedback resistors "next to the FB PIN … **Do not connect FB to these resistors through vias**". R2 to AGND; R1 to the output cap at the regulation point.
  - Sensitive nodes (FB, VCC, AGND) "far from high dv/dt signals"; BST path short.
  - ≥4-layer PCB with Inner1 = PGND only.
  - Source: [MPS AN065](https://media.monolithicpower.com/document/PCB_Layout_Design_Guidelines_for_NB67xSeries.pdf) [P]
- **Rohm 60AN066E Rev.004 (Jan 2024), "PCB Layout Techniques of Buck Converter":**
  - CBYPASS **0.1–0.47 µF** X5R/X7R near the IC terminals on the top layer. Bulk CIN "can be separated about **2cm**" from CBYPASS. Never put both on the reverse side through vias.
  - "Shortening the wiring even by **1mm** is highly recommended."
  - Place CIN and CO grounds "separated from each other by at least **1cm to 2cm**", because input-side HF noise propagates through CO.
  - Free-wheel diode close, on the same surface.
  - Thermal vias 0.3 mm ID at ~**1.2 mm** pitch.
  - Width >**1 mm per A** (1 oz) and >**0.7 mm per A** (2 oz). E.g., 2 A at 35 µm → 0.53 mm for a 20 °C rise.
  - Do not enlarge copper unnecessarily (antenna).
  - FB: short connection to the divider; sense after or across CO; divider parts near each other; "far away from switching node of inductor and diode. **Do not wire directly below the inductor and diode, and not parallel to power supply line**."
  - Via L ≈ (h/5)·(ln(4h/d)+1) nH (Johnson).
  - Source: [Rohm buck layout note](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf) [P]
- **TI SNVA803 (Hegarty, Sept 2019, LM5146-Q1):**
  - Lateral switching loop "almost **20 mm²**", inductance "**greater than 1 nH**" even over an L2 image plane.
  - Vertical loop using L2 as the return: **2 mm²**, "**less than 500 pH**", overshoot ~**4 V** lower.
  - Four **10 nF 0402/0603** input caps at the HS drain, with grounds to L2 through multiple **12 mil (0.3 mm)** vias.
  - SW polygon = inductor pad + minimum FET connection, single-layer SW/BST routing.
  - Source: [TI SNVA803](https://www.ti.com/lit/pdf/snva803) [P]
- **EPC, "Optimizing PCB Layout with eGaN FETs" (Reusch):**
  - High-frequency loop inductance from ~**0.4 nH to 2.9 nH** cut efficiency "by over **4 %**".
  - Overshoot fell "from **100 %** of the input voltage to **30 %**" going from 1.6 nH to 0.4 nH (12 V→1.2 V, 1 MHz).
  - Lateral loops need a minimal distance to the shield layer; the "optimal" layout uses the first inner layer as the return.
  - Source: [EPC layout paper](https://epc-co.com/epc/documents/papers/Optimizing%20PCB%20Layout%20with%20eGaN%20FETs.pdf) [P]
- **TI SLYT682:**
  - Commutation >**5 A/ns** → **2 nH gives 10 V** overshoot.
  - Continuous L2 shield, e.g. a **5-mil** core; avoid vias in the hot loop.
  - Short, wide SW pour with a full GND plane under it on multilayer boards.
  - **Top-layer copper keep-out under the inductor.**
  - Source: [TI SLYT682](https://www.ti.com/lit/pdf/slyt682) [P]
- **ADI AN-139 Table 1 (10 × 10 cm loop, 27 MHz):**
  - 187 nH single-layer; 42 nH over a plane at 1.5 mm; 23 nH at 0.5 mm; 21 nH at 0.27 mm; **13 nH** at 0.12–0.13 mm.
  - A next-layer plane gives ">3× less" inductance than a 1.5 mm 2-layer board and ">14× less" than a single-layer board.
  - Sources: [ADI AN-139 (mirror)](https://theengineer.markallengroup.com/production/content/uploads/2015/01/an139f.pdf) [P]; [ADI AN-139 page](https://www.analog.com/en/resources/app-notes/an-139.html)
- **TI SLYT614:** order Cin → inductor/snubber → Cout/VOS → small-signal → single-point ground; **1 via per amp**; one side — [TI SLYT614](https://www.ti.com/lit/pdf/slyt614) [P]
- **TI SLVA773 (boost):**
  - Output cap close; 1 via per amp; minimal SW area.
  - "Any trace of a sensitive node, such as FB, should be far away from the SW node". Do not run FB parallel to SW.
  - Input-cap ground close to PGND.
  - A large VIN copper area is acceptable (it is quiet).
  - Source: [TI SLVA773](https://www.ti.com/lit/an/slva773/slva773.pdf) [P]
- **TI LM10504:**
  - SW pins direct to the inductor on the top side; "a trace that is wider than **100 mils** increases the copper area and cause too much capacitive loading on the SW pin".
  - Single-point ground for feedback components; FB trace away from SW and inductor.
  - Ground layer as close as possible (L2).
  - Source: [TI LM10504 layout](https://ti.com/document-viewer/LM10504/datasheet/layout) [P]
- **TI datasheets (LM5163, TPS560430-Q1):** divider near the FB pin; sense trace on another layer, shielded by GND from SW, especially for **R_FB > 100 kΩ** — [TI LM5163](https://www.ti.com.cn/document-viewer/cn/LM5163/datasheet/49-ZHCSKD6) [S]; [TI TPS560430-Q1](https://www.ti.com/document-viewer/lit/html/SLUSDF5A/feedback-resistors-t4862777-8) [S]
- **Conflict, output-cap ground position:**
  - Rohm wants Cin and Cout grounds 1–2 cm apart, to stop input HF noise reaching the output.
  - TI SNVA803 uses a U-shaped layout that puts the output caps for a short return to the low-side FET and the input caps, plus split output caps.
  - MPS wants the output-cap GND "close to the IC's PGND".
  - Sources: [Rohm](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf) [P]; [TI SNVA803](https://www.ti.com/lit/pdf/snva803) [P]; [MPS AN065](https://media.monolithicpower.com/document/PCB_Layout_Design_Guidelines_for_NB67xSeries.pdf) [P]
- **Low-authority target:** hot loop <10 mm² (blog) — [Embedded Hardware Design](https://embeddedhardwaredesign.com/dc-dc-buck-converter-pcb-layout-design-guidelines/) [S]

#### Rule table: switching regulators
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| SMPS-CIN | HF input cap distance to IC | **<2 mm** (MPS NB67x); minimize, "even 1 mm matters" (Rohm) | AN065, Rohm [P] | Integrated bucks (use the datasheet value if given) | G: pad-edge distance Cin pads ↔ VIN/PGND pins |
| SMPS-CBULK | Bulk Cin distance | may be ~20 mm from the HF bypass cap | Rohm [P] | | G |
| SMPS-LOOP | Hot-loop area | anchors: 20 mm² lateral → >1 nH; 2 mm² vertical → <0.5 nH. Tiers [D]: ≤2 mm² excellent, ≤10 mm² acceptable, >20 mm² fail | SNVA803 [P] | Buck/boost/half-bridge | G |
| SMPS-L | Loop-inductance impact | 0.4 → 2.9 nH: −4 % efficiency; 1.6 → 0.4 nH: overshoot 100 % → 30 % of Vin | EPC [P] | Fast-edge (GaN, high-di/dt) | S/G estimate |
| SMPS-OVS | Overshoot | V ≈ L × dI/dt (2 nH × 5 A/ns = 10 V) | SLYT682 [P] | | Calc |
| SMPS-L2 | GND plane directly under loop; thin L1–L2 | ≤0.127 mm (5 mil); >3× L reduction vs 1.6 mm 2-layer | SLYT682, AN-139 [P] | ≥4 layers | G |
| SMPS-VIA | Power vias | ≥1 per A; 0.25/0.5 mm (10/20 mil) drill/pad near pins; >20 between input caps (MPS NB67x) | SLYT614, SLVA773, AN065 [P] | | G |
| SMPS-W | Power trace width | ≥1 mm/A (1 oz), ≥0.7 mm/A (2 oz) | Rohm [P] | | K `track_width` per net class |
| SMPS-SW | SW copper | inductor pad + minimal connection; trace ≤2.54 mm (100 mil) wide; no SW/BST vias to far side | SNVA803, LM10504, SLYT682 [P] | | G |
| SMPS-LKO | Top-layer keep-out under inductor | — | SLYT682 [P] (conflicts in earlier file) | | G |
| SMPS-FB | FB divider at FB pin; no vias between divider and FB; sense after Cout; FB trace not under L/diode, not parallel to SW/power, other layer with GND shield | no numeric clearance | AN065, Rohm, SLVA773, LM10504 [P]; LM5163 [S] | All; critical for R_FB > 100 kΩ | G (heuristic divider–FB distance ≤3 mm [D]) |
| SMPS-GND | AGND/PGND single-point near VCC cap (MPS) or per datasheet | — | AN065 [P] | | G |
| SMPS-COUT | Cin–Cout ground separation | **conflict:** ≥10–20 mm (Rohm) vs short common return (TI, MPS) | as cited [P] | | Vendor switch |

### Inferences
- MPS's "<2 mm" is the only vendor-stated Cin distance found. It is a reasonable default `max_distance` for any integrated buck in a small package, overridable by the datasheet.
- With the loop anchors (SNVA803, AN-139, EPC), a placer can compute loop area and L1→L2 dielectric, estimate inductance, then estimate overshoot and efficiency loss, which turns "minimize the loop" into a scoreable objective.

### Gaps
- No vendor-specified SW-to-sensitive-net clearance in mm was found. ADI AN-136 and the Kueck articles were not downloadable (analog.com blocked). The EPC AN026 table was not read.

---

## 9. Board-edge, plane-edge, return-via and stitching rules

### Takeaway
Distance from high-speed traces to the reference-plane edge:
- TI general: **≥90 mil (2.29 mm)**, and ≥1.5 W from voids.
- TI PCIe Gen5: **≥5 × max(W, H)**, and ≥4 H from voids.
- Microchip (SuperSpeed): ≥5 × W from plane edge or split.
- Pulse (Ethernet): "greater than the trace height above the ground plane" from board edges, and PHY plus pairs ≥25 mm from the PCB edge.

Return vias at layer transitions:
- Within **200 mil** (TI general), **100–200 mil with ≥2 vias** (EMA), or **50 mil** (TI Gen5).
- "Next to" the signal via, but not so close as to disturb impedance (Renesas).
- A C-shaped via ring around clock and RF transitions (Qualcomm).

The 20H power-plane pullback rule is not supported by measurements and should not be a default.

### Cited Findings
- **TI SPRAAR7J §3.2 / SLLA414A:**
  - ≥**90 mil (2.29 mm)** from the reference-plane edge; ≥**1.5 W** from voids (SMD-pad voids excepted).
  - Breakout within **0.25 in**.
  - Antipads as large as possible (**30 mil** "good"); no non-functional pads.
  - Stitching caps across unavoidable splits ≤**1 µF**, at the crossing.
  - Sources: [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]; [TI SLLA414A](https://www.ti.com/lit/pdf/slla414) [P]
- **Return vias (TI):** GND stitching vias placed symmetrically **within 200 mil (5.08 mm)** of signal transition vias (SPRAAR7J, SLLA414A); **within 50 mil (1.27 mm)** with "as many as possible" around the antipad (SNLA426) — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]; [TI SNLA426](https://www.ti.com/lit/pdf/snla426) [P]
- **Return vias (EMA):** "Place at least **2 ground stitching vias within 100–200 mils** of each signal via. For differential pairs, place vias on both sides" — [EMA PCIe Design Guide](https://www.ema-eda.com/wp-content/uploads/2025/10/PCIe-Design-Guide-Part-1.pdf) [P]
- **Return vias (Renesas):** GND via next to each signal via, "keep a sufficient distance … so that the signal impedance is not affected"; a stitching cap is not mandatory — [Renesas R31AN0080EU0102](https://www.renesas.com/en/document/apn/pcie-buffer-mux-layout-recommendations?r=1565126) [P]
- **Return vias (Qualcomm):** "All the CLK vias should be completely surrounded … A C-shaped ring of vias should be standard for all clock and RF line transitions." — [Qualcomm CXO routing](https://docs.qualcomm.com/doc/80-PV086-5P/topic/CXO-and-SLEEP_CLK-routing.html) [P]
- **TI SNLA426 (Gen5):** ≥5W or 5×RPH from the plane edge; ≥4×RPH from voids; avoid "edge of the board" — [TI SNLA426 §18](https://www.ti.com/lit/pdf/snla426) [P]
- **Microchip AN26.2:** SS not within **5X trace width** of a plane edge or split; terminate narrow ground floods with vias at all corners and ends — [Microchip AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) [P]
- **Pulse:** "Route traces away from board edges by a distance greater than the trace height above the ground plane". PHY and pairs ≥**25 mm** from the PCB edge — [Pulse](https://www.farnell.com/datasheets/2699973.pdf) [P]
- **20H rule:** Hubing and Shim measured slightly higher radiation with 20H. LearnEMC (Dec 2023) lists it as debunked — [Hubing/Shim](https://scholarsmine.mst.edu/faculty_work/1604) [S]; [LearnEMC QOTW 2023-12-25](https://learnemc.com/qotw-231225) [S]

#### Rule table: edges and returns
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| EDGE-PL | HS trace to reference-plane edge | ≥2.29 mm (TI general); ≥5·max(W,H) (Gen5); ≥5W (Microchip SS) | SPRAAR7J, SNLA426, AN26.2 [P] | ≥1 Gb/s pairs | G (zone-boundary offset; `edge_clearance` covers the board outline only) |
| EDGE-BRD | Any trace to board edge | ≥1·H (Pulse); Ethernet PHY/pairs ≥25 mm | Pulse [P] | | K `edge_clearance` (H from stackup) |
| EDGE-VOID | To plane voids | ≥1.5W / ≥4H | SPRAAR7J, SNLA426 [P] | | G |
| EDGE-RV | GND return vias at layer change | ≥1 (TI) or ≥2 (EMA), symmetric; ≤5.08 mm (≤5 Gb/s class), ≤2.5–5.1 mm (EMA), ≤1.27 mm (Gen4/5) | SPRAAR7J, EMA, SNLA426 [P] | | G |
| EDGE-CLKVIA | Clock/RF via shielding | C-shaped GND via ring | Qualcomm [P] | | G |
| EDGE-BRK | Breakout length | ≤6.35 mm | SPRAAR7J [P] | | G |
| EDGE-SCAP | Stitching cap across split | ≤1 µF at crossing | SPRAAR7J [P] | | G |
| EDGE-20H | 20H pullback | do not enforce by default | Hubing/Shim, LearnEMC [S] | | — |

### Inferences
- The return-via distance should be parameterized by data rate: ~5 mm for ≤5 Gb/s, ~2.5 mm at Gen3/Gen4, ~1.3 mm at Gen5. That matches the scopes of the respective documents.
- Plane-edge offsets are a geometric post-fill check (or a shrunken routing keep-in rule area). KiCad's `edge_clearance` does not cover them.

### Gaps
- No primary numeric via-stitching pitch specific to layer transitions beyond per-via return distance; perimeter stitching stays λ/20 by analogy (earlier file).

---

## 10. Mounting holes, fab capabilities (JLCPCB, PCBWay, OSH Park) and assembly spacing

### Takeaway
Official fab capability pages give these 1 oz limits:

| Parameter | JLCPCB | PCBWay standard | OSH Park |
|---|---|---|---|
| Trace/space | 4/4 mil (1–2 layer), 3.5/3.5 mil (multilayer) | 4/4 mil | 6/6 mil (2-layer), 5/5 mil (4-layer) |
| Drill | min 0.15 mm, 0.2 mm preferred | 0.15–6.0 mm, surcharge <0.2 mm | min 10 mil |
| PTH annular ring | 0.25 mm rec / 0.18 mm abs (2-layer); 0.20 / 0.15 mm (multilayer) | 0.15 mm | 5 mil (2-layer), 4 mil (4-layer) |
| Silkscreen | line ≥0.15 mm, text ≥1.0 mm, pad-to-silk 0.15 mm | character width ≥0.15 mm, height ≥0.8 mm | 5 mil recommended (3 mil for short features) |
| Copper to edge | ≥0.2 mm routed, ≥0.4 mm V-cut | — | 15 mil keep-out |

JLCPCB SMT panels use 5 mm rails, 2 mm tooling holes and 1 mm fiducials at 3.85 mm.

Mounting-hole keep-outs have no published standard. The best primary example is the Raspberry Pi RP2040 reference design: a 2.75 mm NPTH with a 6 mm diameter keep-out (2.7 mm with a 6.2 mm keep-out in other Pi designs). ISO 273 clearance holes for M3 are 3.2/3.4/3.6 mm (secondary table). Component-to-component and component-to-edge assembly spacing remains secondary-sourced.

### Cited Findings

#### JLCPCB (official capabilities page)
- **Trace/space (1 oz):** **0.10/0.10 mm** (1–2 layer), **0.09/0.09 mm** multilayer (3 mil in BGA fan-outs). 2 oz: 0.16 mm (2-layer) / 0.15 mm (multilayer). Track tolerance ±20 % — [JLCPCB PCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities) [P]
- **Drill and holes:**
  - 0.15–6.3 mm (0.1 mm only for ≤1 mm boards with ENIG/OSP).
  - Via ≥0.15 mm hole / 0.25 mm pad; pad = hole + 0.1 mm (+0.15 preferred); **preferred min via hole 0.2 mm**.
  - Via hole-to-hole 0.2 mm; pad hole-to-hole 0.45 mm.
  - Source: [JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities) [P]
- **Annular ring:** PTH 2-layer 1 oz **0.25 mm recommended / 0.18 mm absolute**; multilayer **0.20 / 0.15 mm**; 2 oz ≥0.254 mm; NPTH ring ≥0.45 mm — [JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities) [P]
- **Clearances:**
  - Pad-to-track 0.1 mm (0.09 mm at BGA); SMD pad-to-pad 0.15 mm; min SMD pad 0.25 × 0.25 mm.
  - Via-to-track 0.2 mm; PTH-to-track 0.28 mm (0.35 mm recommended); NPTH-to-track 0.2 mm.
  - Inner via-to-copper 0.2 mm; inner PTH-to-copper 0.3 mm.
  - Mask bridge 0.10 mm (green etc.) / 0.13 mm (black/white).
  - Plugged vias ≤0.5 mm, ≥0.35 mm from openings.
  - Source: [JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities) [P]
- **Legend:** line ≥**0.15 mm**; text height ≥**1.0 mm (40 mil)**; ratio 1:6; pad-to-silk **0.15 mm** — [JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities) [P]
- **Outline and panels:**
  - Copper ≥**0.2 mm** from routed edges and slots, ≥**0.4 mm** from V-cuts.
  - Routed tolerance ±0.2 mm (±0.1 mm precision); V-cut ±0.4 mm, 25°, ≥2 mm between V-cuts (3 mm recommended).
  - Mouse-bite spacing 1.6 or 2 mm; min tooling edge 3 mm. For SMT: **5 mm tooling edges, 2 mm tooling holes, 1 mm fiducials 3.85 mm from the panel edges**.
  - Castellations ≥0.5 mm, 1 mm from the edge.
  - Impedance ±10 % (±5 % on request).
  - Source: [JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities) [P]
- **Assembly:** min IC pitch **0.35 mm** (standard) / **0.40 mm** (economic); BGA pitch 0.3/0.5 mm; 01005 supported; recommended max panel 250 × 250 mm — [JLCPCB assembly capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities) [P]
- **SMD spacing:** JLCPCB's SMD-spacing table is JavaScript-rendered and was not readable. A support reply says component-to-outline clearance = 0.2 mm (routed) / 0.4 mm (V-cut) — [JLCPCB SMD minimum spacing](https://jlcpcb.com/help/article/smd-components-minimum-spacing) [S]; [EasyEDA forum](https://easyeda.com/forum/topic/How-close-can-SMD-components-be-to-the-edge-of-the-PCB-for-JLCPCB-to-assemble-them-2645b5a11aad4f169de4faa8f0857581) [S]

#### PCBWay (official capabilities page)
- Min trace **0.1 mm**, min space **0.1 mm**.
- Drill **0.15–6.0 mm** (surcharge <0.2 mm or >6 mm).
- Annular ring **0.15 mm** for via pads.
- Finished hole tolerance PTH ±0.08 / NPTH ±0.05 mm.
- Legend character width ≥**0.15 mm**, height ≥**0.8 mm**, ratio **1:5**.
- Half-holes ≥0.4 mm.
- Panel spacing 1.6 mm for routing, 0 for V-score.
- Advanced table: line-to-edge 0.25/0.20 mm (CNC milling); impedance ±10 % (±5 Ω at ≤50 Ω).
- Source: [PCBWay capabilities](https://www.pcbway.com/capabilities.html) [P]

#### OSH Park (official docs)
- **2-layer:** 6/6 mil; annular ring **5 mil**; edge keep-out **15 mil**; min drill **10 mil**; drill tolerance ±2.5 mil; 5 mil between holes; no blind, buried or filled vias; silkscreen **5 mil** recommended (3 mil short features) — [OSH Park 2 Layer](https://docs.oshpark.com/services/two-layer/) [P]
- **4-layer:** **5/5 mil**; annular ring **4 mil**; plated drill to inner copper **10 mil**; FR408HR, L1–L2 prepreg **7.87 mil**, core 39 mil — [OSH Park 4 Layer](https://docs.oshpark.com/services/four-layer/) [P]

#### Eurocircuits (classification page)
- The inner-layer pad isolation (IPI) minimum is always IAR + 0.075 mm, with a minimum of 0.200 mm.
- Connected NPTH annular ring ≥**0.30 mm**.
- The full pattern- and drill-class table is an image and was not extracted.
- Source: [Eurocircuits classification](https://www.eurocircuits.com/pcb-design-guidelines-classification/) [P]

#### Mounting holes
- **Raspberry Pi "Hardware design with RP2040" reference schematics:**
  - Minimal design: mounting holes "NPTH FD2.75mm SM3.15mm **KO6mm**" (finished drill 2.75 mm, mask 3.15 mm, keep-out 6 mm diameter).
  - Other Pi reference boards: "FD2.7mm SM5.8mm KO6.2mm".
  - Source: [Raspberry Pi, Hardware design with RP2040](https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf) [P]
- **ISO 273 clearance holes (Optimas table):** M2 2.2/2.4/2.6; M2.5 2.7/2.9/3.1; **M3 3.2/3.4/3.6**; M4 4.3/4.5/4.8 mm (close/medium/free). The mapping to the ISO fine/medium/coarse series is unconfirmed — [Optimas tapping/clearance sizes](https://optimas.com/technical-resources/tapping-sizes/) [S]
- **Practical anchors:** M3 socket-head screw head ≈5.5 mm diameter; ~7 mm clearance used in practice around 3.2 mm holes — [BestPCBs](https://www.bestpcbs.com/blog/?p=36814) [S]; [KiCad forum](https://forum.kicad.info/t/mounting-holes-clearance/10316) [S]
- **TI:** do not route high-speed traces near mounting holes — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]

#### Assembly spacing (no authoritative standard found)
- Cadence: 0.25–0.3 mm side-to-side and 0.5–1 mm to edge — [Cadence DFA](https://resources.pcb.cadence.com/i/1541046/25) [S]
- TI: ≥**0.508 mm** between land areas — [TI SPRAA99C](https://www.ti.com.cn/document-viewer/cn/lit/html/SPRAA99C/GUID-164C9D50-16B4-451B-AE9B-3579FEE28AA7) [S]
- Courtyard defaults 0.25 mm, 1.0 mm around BGAs, ~1.5 mm BGA rework clearance — [Sierra Circuits / various](https://www.protoexpress.com/?p=9130) [S]
- Earlier-file values still apply: IPC-7351 Level B 0.25 mm courtyard; V-score ≥2 mm; MLCC 3–5 mm from V-cuts.

#### Rule table: fab and assembly profiles (DRC minimums; design to "recommended")
| Parameter | JLCPCB 2L (rec / abs) | JLCPCB ML (rec / abs) | PCBWay std | OSH Park 2L | OSH Park 4L | KiCad check |
|---|---|---|---|---|---|---|
| Trace / space (1 oz) | 0.10 / 0.10 mm | 0.09 / 0.09 mm | 0.10 / 0.10 mm | 0.152 / 0.152 mm | 0.127 / 0.127 mm | K `track_width`, `clearance` |
| Min drill | 0.2 pref / 0.15 mm | 0.2 pref / 0.15 mm | 0.15 mm (≥0.2 no surcharge) | 0.254 mm | 0.254 mm | K `hole_size` |
| Annular ring | 0.25 / 0.18 mm | 0.20 / 0.15 mm | 0.15 mm | 0.127 mm | 0.102 mm | K `annular_width` |
| Copper to routed edge | 0.2 mm | 0.2 mm | 0.20–0.25 mm | 0.381 mm | 0.381 mm | K `edge_clearance` |
| Copper to V-cut | 0.4 mm | 0.4 mm | — | — | — | K `edge_clearance` |
| Hole to hole | 0.2 (via) / 0.45 (pad) mm | same | table | 0.127 mm rec | 0.127 mm rec | K `hole_to_hole` |
| Silk line width | ≥0.15 mm | ≥0.15 mm | ≥0.15 mm | 0.127 mm (0.076) | same | K `text_thickness` |
| Silk text height | ≥1.0 mm | ≥1.0 mm | ≥0.8 mm | — | — | K `text_height` |
| Pad-to-silk | 0.15 mm | 0.15 mm | — | — | — | K `silk_clearance` |
| Mask bridge | 0.10 mm (green) / 0.13 mm (black/white) | same | 4 mil class | — | — | DRC |
| Impedance tol. | ±10 % (±5 % req.) | same | ±10 % (±5 Ω ≤50 Ω) | — | — | — |
| Mounting-hole keep-out | — | — | — | — | — | G: courtyard/zone keep-out circle Ø ≥ screw head + 2 × margin (RP2040 example: Ø6 mm around 2.75 mm hole) |

### Inferences
- Fab profiles should be separate packs (precedence 10) that only set `min`, with `recommended` used as the router's `opt`. Interface packs set `opt`/`max` and must never relax fab minimums.
- Mounting-hole keep-out is best derived: keep-out Ø = max(screw-head or standoff Ø + 2 × 0.5 mm, vendor example). RP2040's 6 mm around a 2.75 mm hole is a citable primary data point.

### Gaps
- JLCPCB's component spacing table and PCBWay's assembly spacing were not readable. No standard mounting-hole keep-out exists in the sources found.

---

## 11. Implications for an LLM-driven KiCad placer/router

### Takeaway
A rule only becomes machine-actionable if it carries five things:
1. A match pattern binding it to schematic objects (part class, pin function, net role).
2. Typed parameters with units, including ps and formulas in UI, W or H.
3. Provenance and precedence (datasheet > vendor family guide > interface default > generic), with conflicts recorded rather than silently resolved.
4. A check backend: KiCad DRU emission, a geometric script, or a simulation budget.
5. A placement intent (anchor, adjacency, order along a path, distance window, keep-out), kept separate from routing constraints.

The data above shows why this matters. For the same interface, primary vendor values differ by 5–25× (USB3 skew 2 mil vs 0.7 mm; DDR4 DQ↔DQS 2 ps vs 25 ps; Ethernet PHY↔magnetics ≥25 mm vs <25 mm). KiCad 10's `fromTo()` paths and ps units make most DDR and SerDes rules natively checkable. Plane-edge offsets, loop areas, topology order and return-via distances still need geometric checks.

### Cited Findings
- KiCad 10: `fromTo('RefDes-Pad','RefDes-Pad')` path conditions with wildcards for `length`, `skew`, `track_width`, `clearance` and `diff_pair_gap`; `skew` supports `within_diff_pairs` — [KiCad 10.0 custom rules](https://docs.kicad.org/10.0/en/pcbnew/pcbnew_advanced.html) [P, doc source]
- KiCad 10 time domain: `length`/`skew` in `ps` switch the tuner to propagation-delay mode, e.g. `(constraint length (min 450ps) (opt 500ps) (max 550ps))` and `(constraint skew (max 5ps))`. Time and length units cannot be mixed in one constraint — [KiCad 10.0 time-domain tuning](https://docs.kicad.org/10.0/en/pcbnew/pcbnew_editing.html) [P, doc source]
- TI: match in the tool to <20 % of each ps limit, then simulate — [TI SPRAD06C](https://www.ti.com/lit/pdf/sprad06) [P]

### Inferences

#### Proposed rule-pack schema (YAML)
```yaml
# rulepack schema v0 (proposal)
pack:
  id: <interface-or-circuit id>          # e.g. usb2_hs, buck_sync, xtal_pierce
  version: 0.1
  precedence: 30                          # 10 fab profile < 20 interface default < 30 vendor family < 40 device datasheet
  vendor_profile: <ti|microchip|qualcomm|...|unknown>   # selects among conflicting vendor values
  applies_when:                           # binding to the netlist / BOM
    parts: [ {role: <name>, match: {lib_regex: ..., pin_functions: [...], value_regex: ...}} ]
    nets:  [ {role: <name>, match: {pin: "<role>.<pin_function>"}} ]
  parameters:                             # typed, unit-carrying, overridable
    <name>: {value: <number|formula>, unit: mm|mil|ps|ohm|nF|pF|dB|pct|UI|W|H, tag: P|S|D, source: <url>, rev: <doc rev>,
             by_vendor: {<vendor>: <value>, ...}}      # optional per-vendor alternatives
  conflicts:                              # recorded, never silently resolved
    - {parameter: <name>, values: [{value: .., source: ..}, ...], resolution: stricter|vendor_profile|window|ask}
  placement:                              # intents for the placer (soft scores or hard bounds)
    - {type: anchor|adjacent|order_along_path|distance_window|same_side|keepout_ring|orientation|max_loop_area, ...}
  routing:
    netclasses: [...]
    diff_pairs: [...]
  checks:                                 # every rule names its backend
    - {id: <rule id>, backend: kicad_dru|geometric|simulation|bom, severity: error|warning|info, emit: <template or function>}
```
Resolution policy:
1. Use the highest-precedence pack that defines the parameter.
2. Within one precedence level, use `by_vendor[vendor_profile]` if present.
3. Otherwise apply the declared `resolution`. The default is "stricter", and it must raise an `info` finding that cites both sources.
4. [S] values never override [P] values at equal precedence.
5. [D] heuristics default to `warning` until calibrated against vendor evaluation-board layouts.

#### Worked example 1: USB 2.0 HS device port
```yaml
pack:
  id: usb2_hs
  precedence: 20
  vendor_profile: unknown
  applies_when:
    parts:
      - {role: conn, match: {lib_regex: "USB_(A|B|C|Micro|Mini).*"}}
      - {role: phy,  match: {pin_functions: ["USB_DP","USB_DM"]}}
      - {role: esd,  match: {lib_regex: "(TPD|USBLC|PESD|ESD).*", optional: true}}
      - {role: cmc,  match: {class: common_mode_choke, optional: true}}
    nets:
      - {role: dp, match: {pin: "phy.USB_DP"}}
      - {role: dm, match: {pin: "phy.USB_DM"}}
  parameters:
    zdiff:          {value: 90, unit: ohm, tol_pct: 15, tag: P, source: "https://www.ti.com/lit/pdf/slla414",
                     by_vendor: {qualcomm: "75-105", microchip: "90 +5/-10"}}
    intra_skew_max: {value: 1.27, unit: mm, tag: P, source: "https://www.ti.com/lit/pdf/spraar7",
                     by_vendor: {qualcomm: 2.0, ti_usb_controllers: 3.81}}
    len_warn:       {value: 150, unit: mm, tag: P, source: "https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf"}
    len_max:        {value: 250, unit: mm, tag: P, source: "https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb-2dot0-routing-constraints.html",
                     by_vendor: {ti: 304.8}}
    via_max:        {value: 4, unit: count, tag: P, source: "https://www.ti.com/lit/pdf/spraar7"}
    gap_other_min:  {value: 0.762, unit: mm, tag: P, source: "https://www.ti.com/lit/pdf/spraar7"}   # Microchip: 3*max(W,H)
    gap_clock_min:  {value: 1.27, unit: mm, tag: P, source: "https://www.ti.com/lit/pdf/spraar7"}
    gnd_overhang:   {value: "5*pair_gap", unit: mm, tag: P, source: "https://ww1.microchip.com/downloads/en/Appnotes/AN13.10-Application-Note-DS00002972A.pdf"}
    esd_conn_max:   {value: 5.0, unit: mm, tag: D, source: "heuristic; TI: 'as close as possible' (SLVA680A, TPD6S300A)"}
  conflicts:
    - {parameter: intra_skew_max, values: [{value: 0.05, source: "SPRAAR7A (2013)"}, {value: 1.27, source: SPRAAR7J}, {value: 2.0, source: Qualcomm}, {value: 3.81, source: TUSB9261}], resolution: vendor_profile}
    - {parameter: shield_termination, values: [{value: "330R||100nF", source: "Microchip AN26.2"}, {value: "ferrite 10-50R@100MHz", source: "TI SPRAAR7A"}, {value: "AC-only on device", source: "Microchip AN13.10"}], resolution: ask}
  placement:
    - {type: anchor, part: conn, edge: board_edge}
    - {type: order_along_path, path: [conn.DP, esd, cmc, phy.USB_DP], also: [conn.DM, esd, cmc, phy.USB_DM]}
    - {type: distance_window, a: esd, b: conn, max: esd_conn_max}
  routing:
    netclasses: [{name: USB2, nets: [dp, dm], width: from_stackup(zdiff), diff_gap: from_stackup(zdiff)}]
  checks:
    - {id: USB2-SKEW, backend: kicad_dru, emit: |
        (rule "USB2 intra-pair skew"
          (condition "A.hasNetclass('USB2')")
          (constraint skew (max ${intra_skew_max}mm) (within_diff_pairs)))}   # verify token form on installed KiCad
    - {id: USB2-VIA, backend: kicad_dru, emit: |
        (rule "USB2 vias" (condition "A.hasNetclass('USB2')") (constraint via_count (max 4)))}
    - {id: USB2-LEN, backend: kicad_dru, emit: |
        (rule "USB2 length" (condition "A.fromTo('${conn.ref}-*', '${phy.ref}-*') && A.hasNetclass('USB2')")
          (constraint length (max ${len_max}mm)))}
    - {id: USB2-SP, backend: kicad_dru, emit: |
        (rule "USB2 to others" (condition "A.hasNetclass('USB2') && !B.hasNetclass('USB2')") (constraint clearance (min 0.762mm)))}
    - {id: USB2-STUB, backend: geometric, emit: no_t_junctions_or_testpoints(nets=[dp,dm])}
    - {id: USB2-REF,  backend: geometric, emit: gnd_zone_covers(offset_polygon(nets=[dp,dm], gnd_overhang))}
    - {id: ESD-PATH,  backend: geometric, emit: path_order_and_zero_vias(conn->esd) and gnd_via_within(esd.GND, 1.0mm)}
    - {id: USB2-AC,   backend: bom, emit: no_series_caps(nets=[dp,dm])}
```

#### Worked example 2: synchronous buck (integrated FETs)
```yaml
pack:
  id: buck_sync
  precedence: 20
  applies_when:
    parts:
      - {role: ic,      match: {pin_functions: ["VIN","SW","PGND|GND","FB"]}}
      - {role: cin_hf,  match: {class: capacitor, nets: ["ic.VIN","ic.PGND"], value_le: "1uF"}, prefer_smallest_package: true}
      - {role: cin_bulk,match: {class: capacitor, nets: ["ic.VIN","ic.PGND"], value_gt: "1uF"}, optional: true}
      - {role: ind,     match: {class: inductor, nets_any: ["ic.SW"]}}
      - {role: cout,    match: {class: capacitor, nets: ["VOUT","GND"]}}
      - {role: rfb_top, match: {class: resistor, nets: ["ic.FB","VOUT"]}}
      - {role: rfb_bot, match: {class: resistor, nets: ["ic.FB","AGND|GND"]}}
  parameters:
    cin_dist_max:    {value: 2.0, unit: mm, tag: P, source: "https://media.monolithicpower.com/document/PCB_Layout_Design_Guidelines_for_NB67xSeries.pdf"}
    cbulk_dist_max:  {value: 20,  unit: mm, tag: P, source: "https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf"}
    loop_area_good:  {value: 2,   unit: mm2, tag: P, source: "https://www.ti.com/lit/pdf/snva803"}   # measured <0.5 nH
    loop_area_fail:  {value: 20,  unit: mm2, tag: P, source: "https://www.ti.com/lit/pdf/snva803"}   # measured >1 nH
    loop_area_warn:  {value: 10,  unit: mm2, tag: S, source: "https://embeddedhardwaredesign.com/dc-dc-buck-converter-pcb-layout-design-guidelines/"}
    didt:            {value: 5,   unit: A/ns, tag: P, source: "https://www.ti.com/lit/pdf/slyt682"}
    l1_l2_max:       {value: 0.127, unit: mm, tag: P, source: "https://www.ti.com/lit/pdf/slyt682"}
    vias_per_amp:    {value: 1,   unit: count/A, tag: P, source: "https://www.ti.com/lit/pdf/slyt614"}
    pwr_width_per_A: {value: 1.0, unit: mm/A, tag: P, source: "Rohm 60AN066E (1 oz); 0.7 mm/A at 2 oz"}
    sw_trace_w_max:  {value: 2.54, unit: mm, tag: P, source: "https://ti.com/document-viewer/LM10504/datasheet/layout"}
    fb_div_max_dist: {value: 3,   unit: mm, tag: D, source: "uncalibrated; MPS/TI say 'next to FB pin'"}
  conflicts:
    - {parameter: cout_gnd_vs_cin_gnd, values: [{value: ">=10-20 mm apart", source: Rohm}, {value: "short common return", source: "TI SNVA803, MPS AN065"}], resolution: vendor_profile}
    - {parameter: copper_under_inductor_top, values: [{value: keepout, source: "TI SLYT682"}, {value: "per datasheet", source: "earlier file"}], resolution: stricter}
  placement:                                   # SLYT614 order
    - {type: priority_order, parts: [cin_hf, ind, cout, rfb_top, rfb_bot, cin_bulk]}
    - {type: same_side, parts: [ic, cin_hf, ind, cout]}
    - {type: distance_window, a: cin_hf.pads, b: [ic.VIN, ic.PGND], max: cin_dist_max, hard: true}
    - {type: distance_window, a: cin_bulk, b: cin_hf, max: cbulk_dist_max}
    - {type: max_loop_area, loop: [cin_hf.+, ic.VIN, ic.PGND, cin_hf.-], target: loop_area_good, warn: loop_area_warn, fail: loop_area_fail}
    - {type: distance_window, a: rfb_top, b: ic.FB, max: fb_div_max_dist}
    - {type: keepout_ring, around: ind, layers: [F.Cu], nets_disallowed: ["*"], except: [ind.pads]}
  routing:
    sw_copper: {max_area: "ind.pad_area + min_connection", max_width: sw_trace_w_max, vias_on_sw: 0}
    fb_trace:  {vias_between_divider_and_FB: 0, layer: "!= layer_of(SW)", shield: "GND plane between", keep_away_from: [SW, ind, diode, VIN], not_parallel_to: [SW, VIN]}
    power:     {width_min: "I_max * pwr_width_per_A", vias_at_layer_change: "ceil(I_max * vias_per_amp)"}
  checks:
    - {id: SMPS-CIN,  backend: geometric, emit: pad_edge_distance(cin_hf, [ic.VIN, ic.PGND]) <= cin_dist_max}
    - {id: SMPS-LOOP, backend: geometric, emit: loop_polygon_area_and_L_estimate(ref=[[20mm2,">1nH"],[2mm2,"<0.5nH"]], plane_height=l1_l2)}
    - {id: SMPS-OVS,  backend: geometric, emit: overshoot = L_est * didt; warn if > 0.2 * Vds_max}
    - {id: SMPS-L2,   backend: geometric, emit: zone_covers(loop_polygon, layer=next_inner, net=GND)}
    - {id: SMPS-VIA,  backend: geometric, emit: via_count(net in [VIN,VOUT], at=layer_change) >= ceil(I_max*vias_per_amp)}
    - {id: SMPS-FB,   backend: geometric, emit: fb_checks()}
  overrides:
    datasheet_reference_layout: {if_present: true, target_loop_area: measured_from_eval_board, precedence: 40}
```

#### Worked example 3: MCU Pierce crystal
```yaml
pack:
  id: xtal_pierce
  precedence: 20
  applies_when:
    parts:
      - {role: mcu,  match: {pin_functions: ["OSC_IN|XTAL1|XIN|XTAL_P", "OSC_OUT|XTAL2|XOUT|XTAL_N"]}}
      - {role: xtal, match: {class: crystal}}
      - {role: cl1,  match: {class: capacitor, nets: ["mcu.OSC_IN", GND]}}
      - {role: cl2,  match: {class: capacitor, nets: ["mcu.OSC_OUT", GND]}}
      - {role: rser, match: {class: resistor, in_series_with: xtal, optional: true}}
  parameters:
    dist_max:       {value: 12, unit: mm, tag: P, source: "https://onlinedocs.microchip.com/oxy/GUID-E48B4A26-F201-4F0A-BCBA-16461582816A-en-US-4/GUID-AA04B64F-3C38-4E1C-8B51-49DE3CFE2419.html"}
    dist_min:       {value: 0, unit: mm, tag: P, by_vendor: {espressif_esp32: 2.7, espressif_esp32s3: 2.0},
                     source: "https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html"}
    c_par_xin_max:  {value: 1.0, unit: pF, tag: P, source: "https://www.insidegadgets.com/wp-content/uploads/2013/02/Best-Practices-for-the-PCB-layout-of-oscillators.pdf"}
    c_par_xout_max: {value: 2.0, unit: pF, tag: P, source: "AVR186"}
    c_par_x2x_max:  {value: 0.5, unit: pF, tag: P, source: "AVR186"}
    hs_keepout:     {value: 3, unit: mm, tag: D, source: "uncalibrated; TI SPRAAR7J/Espressif give no number"}
    metal_can_gnd:  {value: vendor_switch, by_vendor: {st: "not to osc GND", ti: "to ground", microchip_avr: "to ground"}, tag: P,
                     source: ["https://ecsxtal.com/store/pdf/stm32-microcontroller-application-note-092823.pdf", "https://www.ti.com/lit/pdf/slaa322"]}
  conflicts:
    - {parameter: copper_under_crystal, values: [{value: "solid/clean ground", source: "Microchip DS, AVR186, SLAA322D, SWRA495L, Espressif"}, {value: "cut planes", source: "TI CDCE925 (S)"}], resolution: "ground for MCU Pierce; cut only when the device datasheet asks"}
  placement:
    - {type: same_side, parts: [mcu, xtal, cl1, cl2]}
    - {type: distance_window, a: [xtal, cl1, cl2], b: [mcu.OSC_IN, mcu.OSC_OUT], min: dist_min, max: dist_max, objective: minimize}
    - {type: adjacent, a: [cl1, cl2], b: xtal, note: "caps on both sides of crystal; cl1 (XIN) first"}
    - {type: adjacent, a: rser, b: mcu, note: "series parts near chip side (Espressif)"}
    - {type: keepout_ring, around: [xtal, cl1, cl2, osc_traces], margin: hs_keepout, nets_disallowed: ["!osc_nets & !GND"], layers: [F.Cu, In1.Cu]}
    - {type: keepout_ring, around: xtal, margin: hs_keepout, part_classes_disallowed: [inductor, transformer]}
  routing:
    guard: {type: gnd_pour_ring, stitch_vias: dense, tie: "single short connection to nearest MCU GND/AVSS"}
    xin_xout_separation: {min: "3 * W", tag: D}
    testpoints_on_osc_nets: 0
  checks:
    - {id: XTAL-DIST,  backend: geometric, emit: dist_min <= max_pad_distance(group=[xtal,cl1,cl2], to=osc_pins) <= dist_max}
    - {id: XTAL-PAR,   backend: geometric, emit: trace_capacitance(osc_nets, stackup) <= c_par_*}
    - {id: XTAL-GUARD, backend: kicad_dru, emit: |
        (rule "No foreign nets in crystal area"
          (condition "A.insideArea('XTAL_KEEPOUT') && !A.hasNetclass('OSC') && A.Net != 'GND'")
          (constraint disallow track via))}   # verify insideArea syntax on installed KiCad
    - {id: XTAL-TP,    backend: geometric, emit: no_testpoints(osc_nets)}
```

#### Further design implications
- **Vendor profiles are mandatory, not optional.** Without `vendor_profile`, the generator would have to pick among values that differ by 5–25×. The default for unknown vendors should be the tightest primary value, with an `info` finding naming the looser alternatives.
- **Express budgets as physics, not lengths.** For SerDes, store the dB budget, the dB/in table per material, per-via penalties (TI SLLU149E ≈2 in per via; Heck ≈1 in per via) and per-component penalties (Heck: ESD + CMC ≈1 in). Then compute L_max per board stackup.
- **Delay-based packs** (DDR, HDMI, D-PHY, RGMII, SD) should emit ps rules directly (KiCad 10 time domain), use TI's "<20 % of limit" derating as `opt`, and keep the full limit as `max`.
- **Fab profiles** (precedence 10) set `min` only. Interface packs set `opt`/`max`, which prevents relaxing a fab minimum.

### Gaps
- The YAML schema is a proposal. The emitted DRU forms (`within_diff_pairs` token form, `insideArea` vs rule-area naming, `track_angle`) must be tested on the installed KiCad 10 build.
- The geometric backends (loop area, plane-edge offset, return-via distance, topology order, distance windows) are specified only as function names. No open-source KiCad plugin implementing all of them was identified in this pass.
