# Interface- and Circuit-Specific Numeric Layout Rule Packs (supplement to rules_highspeed_emi.md and rules_power_rf_analog_dfm.md)

Scope: numeric gaps left by the two earlier rule catalogs (USB/USB-C/USB4, PCIe Gen3–5, DDR3/DDR4/LPDDR4 tables, Ethernet/HDMI/DP/MIPI/SATA/CAN/RS-485/I2C, crystals, switching-regulator loop numbers, board-edge and return-via rules, fab/assembly limits), plus a proposed rule-pack format.

Provenance tags used on every number:
- **[P]** = read in this session from the primary document (vendor PDF or official fab capability page fetched with curl and converted with pdftotext). Document revision is given where printed.
- **[S]** = search-result snippet only (page could not be fetched or was JavaScript-rendered). Treat as lower confidence.
- **[D]** = derived/computed by me from cited numbers (not stated by the source).

Unit note: 1 mil = 0.0254 mm. Where a source gives mils, mm are added in parentheses. "W" = trace width, "H"/"RPH" = height of trace above its reference plane.

Check-type codes used in the "Auto-check" columns:
- **K** = native KiCad custom-rule constraint (KiCad 10 constraint names: `length`, `skew` (with `within_diff_pairs`), `via_count`, `diff_pair_gap`, `diff_pair_uncoupled`, `edge_clearance`, `clearance`, `track_width`, `hole_size`, `annular_width`, `text_height`, `text_thickness`, `silk_clearance`, `courtyard_clearance`, `hole_to_hole`, `physical_clearance`, etc.). KiCad 10 also supports pad-to-pad path conditions `A.fromTo('U1-A*','U2-B*')` and time units (`ps`) in `length`/`skew`, which switches the tuner to the time domain — [KiCad 10.0 PCB Editor, advanced/custom rules](https://docs.kicad.org/10.0/en/pcbnew/pcbnew_advanced.html); [KiCad 10.0 PCB Editor, time-domain tuning](https://docs.kicad.org/10.0/en/pcbnew/pcbnew_editing.html) [P, read from the 10.0 documentation source].
- **G** = geometric check written against the board model (pcbnew Python / IPC API): distances between pads, polygon areas, plane-edge offsets, topology order.
- **S** = needs SI/PI simulation or a loss calculator; the rule pack can only carry the budget.
- **M** = schematic/BOM-level check (component value, package size), not geometric.

---

## 1. USB 2.0 HS, USB 3.x / USB4, USB Type-C (CC, SBU, orientation, ESD)

### Takeaway
USB 2.0 HS is forgiving: 90 Ω ±15 %, intra-pair mismatch ≤50 mil (1.27 mm), ≤4 vias per trace, no stubs, no AC caps, and total length up to ~12 in on TI SoC boards (Microchip warns that more than ~6 in "may significantly degrade" quality). SuperSpeed is about 10× tighter on skew (≤5 mil / 0.127 mm), allows ≤2 vias per trace, needs 75–265 nF AC caps on TX (220 nF is the common choice), and wants the smallest possible cap package with the reference plane voided under the pads. The USB-C-specific numbers that matter for layout are CC trace ≥8 mil (VCONN up to 600 mA), total CC capacitance in the 200–600 pF cReceiver window, protection parts at the receptacle with no via between connector and TVS pin, and no passives (not even 0 Ω) between the PD controller's CC pin and the receptacle. Primary USB-IF documents were not readable; all numbers come from TI, Microchip and Intel (USB-IF DevCon) material.

### Cited Findings

#### USB 2.0 HS (480 Mb/s)
- TI SLLA414A (Rev. Jan 2026), protocol table for USB 2.0: no AC coupling capacitors allowed, no polarity reversal, 90 Ω ±15 % differential and 45 Ω ±15 % single-ended, 5 m max cable — [TI SLLA414A](https://www.ti.com/lit/pdf/slla414) [P]
- TI SPRAAR7J (Rev. Feb 2023) device table (AM57xx/DRA7xx): USB2 total trace length typ 4000 mil (101.6 mm), **max 12000 mil (304.8 mm)**; skew within the pair ≤**50 mil (1.27 mm)**; Zdiff 81–90–99 Ω; Zcm 40.5–45–49.5 Ω; **0 stubs**; **≤4 vias per trace**; spacing to clock/periodic signals ≥**50 mil (1.27 mm)**; to any other signal ≥**30 mil (0.76 mm)**. The same USB2 rows repeat in the AM335x, KeyStone II, K2G, AM65xx and AM62x tables — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- TI AM335x guide: maximum DP/DM mismatch **150 mil** (looser than the 50 mil above). An older Intel-derived guideline quoted by TI keeps DP/DM ≤4 in — [TI SPRABT8A](https://www.ti.com/lit/an/sprabt8a/sprabt8a.pdf) [S]; [TI USB 2.0 Board Design and Layout Guidelines (E2E China copy)](https://e2echina.ti.com/cfs-file/__key/telligent-evolution-components-attachments/13-106-00-00-00-00-33-10/USB-2.0-Board-Design-and-Layout-Guidelines.pdf) [S]
- Microchip AN26.2 (USB57x4/USB553x hubs): DP/DM Zdiff 90 Ω **+5/−10 Ω**; Z0 40–55 Ω; HS pair members within **1.25 mm (50 mil)**; "Traces longer than ~15 cm (~6 in) may significantly degrade signal quality"; gap from HS pair to other signals ≥**3X**, where X = max(trace width, dielectric height). Worked examples: W = 8 mil, H = 4.3 mil → 24 mil; W = 12 mil, H = 22 mil → 66 mil. Meanders: amplitude ≤3X, gap ≥5X. Avoid any stubs — [Microchip AN26.2 (DS00001876B)](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) [P]
- Connector entry (TI): for a through-hole receptacle (e.g., USB Standard-A), connect high-speed pairs on the **bottom** layer so that the TH pin is part of the path rather than a stub. For SMT receptacles (Micro-B/AB), connect on the top layer, with no vias. Microchip: "sanitize" TH pad stacks by removing unused-layer pads, and increase clearance around these pins to **≥0.5 mm** on all layers — [TI SPRAAR7J §3.5](https://www.ti.com/lit/pdf/spraar7) [P]; [Microchip AN26.2 §3.6.6](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) [P]
- Cable shield: Microchip saw positive EMI/ESD behavior when tying the USB cable shield to digital ground through **330 Ω ∥ 0.1 µF** at each connector on stand-alone designs. Embedded systems may need a direct connection — [Microchip AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) [P]

#### USB 3.x SuperSpeed / USB4
- TI SLLA414A protocol table ("USB 4.0, 3.2 Gen1/Gen2"): Gen1 2.5 GHz (5 Gb/s), Gen2 5 GHz (10 Gb/s), USB4 Gen3 10 GHz (20 Gb/s NRZ), USB4 Gen4 20 GHz (40 Gb/s PAM3). AC caps required on TX, optional on RX. Polarity reversal allowed on SSTX/SSRX. Max intra-pair skew **15 ps/m ("TI recommends 5 mils")**; no inter-pair requirement; 90 Ω ±15 % diff / 45 Ω ±15 % SE; 3 m max cable — [TI SLLA414A](https://www.ti.com/lit/pdf/slla414) [P]
- Impedance targets disagree across sources. SPRAAR7J AM57xx: SSTX/SSRX 83.7–90–96.3 Ω (±7 %). SPRAAR7J AM65xx: USB3.1 Gen1 90.25–95–99.75 Ω (95 Ω ±5 %). Microchip AN26.2: SS **85 Ω ±5 Ω**. One secondary summary: USB4 Gen3 85 Ω ±7 % — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]; [Microchip AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) [P]; [PCBSync USB-C/USB4 guide](https://pcbsync.com/?p=31209) [S]
- Skew and vias: within-pair skew ≤**5 mil (0.127 mm)** and ≤**2 vias per USB3 trace** (SPRAAR7J tables). Microchip: SS pair members within **0.13 mm (5 mil)**; TX and RX pairs need not match each other. If SS signals change layers, add complementary ground vias — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]; [Microchip AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) [P]
- Max length (device-specific, TI): USB3.0 SS total ≤**3500 mil (88.9 mm)** on AM57xx; ≤**5500 mil (139.7 mm)** on KeyStone II; USB3.1 Gen1 ≤**4000 mil (101.6 mm)** on AM65xx — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- Intel/USB-IF DevCon ("SuperSpeed USB Design Guidelines", Howard Heck, Intel) at 5 Gb/s: host PCB length 2–12 in, device PCB length 1–4 in; channel insertion loss −6 to −20 dB with cable loss −7.5 dB (spec max); stub-induced reflections "cost up to 1 in of routing per via"; bottom-side connector entry recommended; ESD + common-mode choke "reduces max route length by ~1 in"; incorporate 100 % voids under the CMC and ESD; use 0402 0 Ω resistors as CMC no-stuff options; on the device side keep trace length ≤2 in; pair-to-pair spacing 0.020–0.040 in depending on interleaving. The slide text extraction was partly garbled, so the spacing numbers are lower confidence — [Heck, USB-IF DevCon slides](https://community.infineon.com/gfawx74859/attachments/gfawx74859/usb-superspeed-peripherals/18243/1/2-4_SSUSB_DevCon_DesignGuidelines_Heck.pdf) [P, partially legible]
- Microchip: SS trace width **≥7.5 mil** while holding target impedance, to reduce loss; SS spacing to all other signals ≥**5X** (e.g., 7 mil → ≥35 mil / 0.89 mm); SS signals not within **5X trace width of a reference-plane edge or split** — [Microchip AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) [P]
- AC-coupling value: USB 3.2 total series capacitance **75–265 nF** (TI forum citing the spec; TI TMUXHS4212 user guide says the same for Gen1/Gen2). **220 nF** on TX is the common choice (it stays compliant if the far end adds its own series cap). For Type-C redriver designs a TI engineer suggests 220 nF on TX and an optional **330 nF** on RX. Congatec uses 330 nF on RX for ESD/EOS help — [TI E2E TUSB1044](https://e2e.ti.com/support/interface-group/interface/f/interface-forum/724790/tusb1044-about-tx-and-rx-ac-coupling) [S]; [TI SLAU823 TMUXHS4212 UG](https://www.ti.com/document-viewer/lit/html/SLAU823/ac-coupling-capacitors-x1260) [S]; [Congatec AN37](https://wiki.congatec.com/wiki/USB_3.2_Gen2_Carrier_Board_Design_Considerations_(AN37)) [S]
- AC-cap package and pad treatment: maximum package **0603**, 0402 or smaller "strongly recommended", placed symmetrically. SLLA414A adds 0201 to minimize inductance and voiding the reference plane under the SMD pads **100 %, at least two layers deep**. SPRAAR7J's ESD/EMI section says **60 %** voids under ESD/EMI component signal pads. Treat 60 % vs 100 % as a conflict and resolve per stackup by TDR/simulation — [TI SLLA414A §4.10](https://www.ti.com/lit/pdf/slla414) [P]; [TI SPRAAR7J §3.10, §3.14](https://www.ti.com/lit/pdf/spraar7) [P]
- In-line part order (TI): ESD/EMI devices as close to the connector as possible. Put AC caps on the **protected side** of the common-mode filter, as close as possible to it. Keep the AC caps + CMF + ESD chain as short and close to the connector as possible — [TI SPRAAR7J §3.14](https://www.ti.com/lit/pdf/spraar7) [P]
- Cap-to-redriver distance: TUSB1002A material sets a **minimum** cap distance of **0.25 in (6.35 mm)** from the redriver, because pad reflections close to the pins return to the device — [TI E2E TUSB1002 AC caps](https://e2e.ti.com/support/interface-group/interface/f/interface-forum/656208/tusb1002-ac-coupling-capacitors-for-usb-3-1-gen-2) [S]; [TUSB1002A datasheet mirror](https://www.alldatasheet.net/html-pdf/2236649/TI2/TUSB1002AI/1433/20/TUSB1002AI.html) [S]
- USB4 budgets (secondary, low confidence): link-partner loss budget said to shrink from 8.5 dB to 5.5 dB at the 10 G rate. The USB 3.2 Gen2 8.5 dB host-to-connector budget limits trace length to about 5 in. One summary gives USB4 Gen3 skew <3 mil and ~60 mm max on standard stacks. The attribution of individual numbers among these pages is uncertain — [Microcontroller Tips USB4 FAQ](https://www.microcontrollertips.com/how-to-test-usb4-designs-faq/) [S]; [Altium USB4 design](https://resources.altium.com/p/usb-4-design-ultra-fast-serial-data-transfer-your-pcb) [S]; [PCBSync](https://pcbsync.com/?p=31209) [S]

#### USB Type-C: CC, SBU, ESD, orientation
- CC capacitance: the USB PD spec (§5.8.6) sets cReceiver at **200–600 pF**. Controller + protection device + any external cap must sum inside that window. TI's TPD6S300A example picks a **220 pF 0201** X7R cap and budgets ±50 % for temperature — [TI TPD6S300A, CC line capacitance](https://www.ti.com/document-viewer/TPD6S300A/datasheet/cc-line-capacitance-t4582032-9) [S]; [TI TPD4S201-Q1](https://www.ti.com/document-viewer/lit/html/SLVSI17/GUID-51D280C8-EB04-44A3-963E-3B88E8A7E749) [S]
- CC routing width: **≥8 mil** CC traces to carry VCONN for powered cables. TPS65988DK minimum widths: CC1/CC2/PP_CABLE 8 mil, VIN_3V3/LDO 6 mil, component GND 10 mil, GPIO 4 mil; capacitor GND pin 16 mil where possible. VCONN delivers up to **600 mA** when Ra is present — [TI TPS65987D layout](https://www.ti.com.cn/document-viewer/cn/TPS65987D/datasheet/GUID-5307ED2F-52B0-4A1F-9169-9D21EC2AC8C5) [S]; [TI TPS65988DK](https://ti.com/document-viewer/lit/html/SLVSFN9A/GUID-9DBFBBE2-2864-4C26-8B17-9D1D5E6F561F) [S]; [TI SLVA888C](https://www.ti.com/document-viewer/lit/html/SLVA888C/GUID-00F49BD1-806B-4083-9CBB-C3D4B1A79D6E) [S]
- Connect the PD controller's CC pins **directly** to the receptacle, with no passive components (not even 0 Ω) between them — [TI SLVA888C](https://www.ti.com/document-viewer/lit/html/SLVA888C/GUID-00F49BD1-806B-4083-9CBB-C3D4B1A79D6E) [S]
- TPD6S300A (CC/SBU/D± protection) layout: place the device as close to the connector as possible. Keep unprotected traces away from the protected traces between device and connector. Route USB2 and SBU lines as straight as possible, and use rounded corners with the largest radii possible on protected traces. Do not drop a via onto the D1/D2 pins from another layer; via the trace to the pin's layer and continue on that layer. VBIAS gets a 0.1 µF cap. Bypass caps on VPWR go close to the pin over solid ground — [TI TPD6S300A datasheet §11](https://www.ti.com/lit/ds/symlink/tpd6s300a.pdf) [P]
- General ESD numbers (TI SLVA680A, Rev. Apr 2022): an IEC 61000-4-2 8 kV strike has dI/dt = 30 A / 0.8 ns = **4×10¹⁰ A/s**, so **0.25 nH adds 10 V** at the protected IC. A 90° corner on the strike path develops ≥7 kV field, which arcs for radii below about **2.6 mm** in air; use curves or ≤45° corners. Avoid vias between the ESD source and the TVS; if a via is unavoidable, route connector → TVS pin first and via afterwards. No stub between the TVS and the protected line. Put a GND via **immediately adjacent** to the TVS ground pin, stitched to an adjacent-layer ground plane — [TI SLVA680A](https://www.ti.com/lit/pdf/slva680) [P]
- Orientation-mux/AC-cap/ESD ordering behind a Type-C receptacle: one PCB vendor blog orders receptacle → ESD → orientation switch → AC caps → VBUS protection, and a second puts the CMC before the AC caps. TI's rule (AC caps on the protected side of the CMF) is the only primary statement found. No primary numeric distance for the mux was found — [BestPCBs USB-C](https://www.bestpcbs.com/blog/2026/08/usb-c-pcb-design/) [S]; [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]

#### Rule table: USB
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| USB2-Z | Diff / SE impedance | 90 Ω ±15 % (81–99 Ω) / 45 Ω ±15 %; Microchip 90 +5/−10 Ω | SLLA414A, SPRAAR7J, AN26.2 [P] | All USB 2.0 HS | K: net class + diff-pair width/gap from stackup solver; S for verification |
| USB2-SKEW | Intra-pair length mismatch | ≤1.27 mm (50 mil); AM335x allows 3.81 mm (150 mil) | SPRAAR7J, AN26.2 [P]; SPRABT8A [S] | HS pairs | K: `skew (max 1.27mm)` + `within_diff_pairs` |
| USB2-LEN | Total length | typ ≤101.6 mm, max 304.8 mm (TI); quality degrades above ~150 mm (Microchip) | SPRAAR7J, AN26.2 [P] | Connector→PHY | K: `length (max …)` with `fromTo('J*-D*','U*-…')` |
| USB2-VIA | Vias per trace | ≤4 | SPRAAR7J [P] | | K: `via_count (max 4)` |
| USB2-STUB | Stubs / test points | 0 / 0 | SPRAAR7J [P] | | G: topology check (no T-junctions; no TP pads on net) |
| USB2-SP | Spacing to other nets / clocks | ≥0.76 mm / ≥1.27 mm (TI); ≥3·max(W,H) (Microchip) | SPRAAR7J, AN26.2 [P] | | K: `clearance` rule between net classes |
| USB2-AC | No AC caps, no P/N swap | — | SLLA414A [P] | | M |
| USB2-TH | TH receptacle: enter on bottom layer; SMT: top layer, no vias | — | SPRAAR7J [P] | | G: layer of last segment at connector pad |
| USB3-Z | SS diff impedance | 90 Ω ±7–15 % (TI) or 85 Ω ±5 Ω (Microchip): device-specific | SPRAAR7J, SLLA414A, AN26.2 [P] | 5/10 Gb/s | K + S |
| USB3-SKEW | Intra-pair | ≤0.127 mm (5 mil) | SPRAAR7J, AN26.2 [P] | | K: `skew (max 0.127mm)` + `within_diff_pairs` (or `max 1ps`-class time rule) |
| USB3-VIA | Vias per trace | ≤2; add GND return vias at each transition | SPRAAR7J, AN26.2 [P] | | K: `via_count (max 2)`; G: GND via within distance (see EDGE-RV) |
| USB3-LEN | Max length | device tables 88.9–139.7 mm; Intel device side ≤2 in (50.8 mm); each via ≈ −1 in; ESD+CMC ≈ −1 in | SPRAAR7J, Heck [P] | | K: `length`; S: loss budget |
| USB3-ACV | TX AC cap value | 75–265 nF total; 220 nF typical; RX optional 330 nF | TI E2E, SLAU823 [S] | Gen1/Gen2 | M: BOM check |
| USB3-ACPKG | AC cap package / pad void | ≤0603, prefer 0402/0201; void reference under pads (100 %, ≥2 layers per SLLA414A; 60 % per SPRAAR7J) | SLLA414A, SPRAAR7J [P] | | M (package); G: zone keep-out polygon under pads present |
| USB3-ORDER | Chain order and proximity | connector → ESD → CMF → AC caps (protected side of CMF), all as close to connector as possible; caps ≥6.35 mm from a redriver | SPRAAR7J [P]; TUSB1002A [S] | Host/device ports | G: graph order along net + pad-distance bounds |
| USBC-CC | CC trace width | ≥0.2 mm (8 mil) | TPS65987D/88DK [S] | Type-C with VCONN | K: `track_width (min 0.2mm)` on CC nets |
| USBC-CCC | CC total capacitance | 200–600 pF incl. controller + protection | PD spec via TI [S] | Type-C | M: sum of datasheet C + cap value |
| USBC-DIRECT | No series passives on CC | 0 | SLVA888C [S] | TI PD controllers | M/G: CC net has exactly controller pin + receptacle pin (+ shunt cap/TVS) |
| ESD-PATH | TVS topology | connector→TVS pin with no via and no stub; GND via adjacent to TVS GND pad; ≤45° or curved corners | SLVA680A, TPD6S300A [P] | All external I/O | G: path order, via count on connector→TVS segment = 0, GND-via distance |

### Inferences
- The USB 2.0 rule set is safe to apply by default on any board. The USB 3.x set should default to TI's 90 Ω / 5 mil / 2-via profile, but the impedance target should be a per-PHY override (85 vs 90 vs 95 Ω all appear in primary docs).
- The 15 ps/m SLLA414A figure is a cable/channel metric. For PCB use, TI's own 5 mil equivalent is the actionable number. A time-domain rule (`skew (max 0.75ps)`-class) is equivalent on FR-4 to ~5 mil [D: ~6–7 ps/in stripline].
- Heck's "1 in per via" and "~1 in per ESD+CMC" conversions are a useful heuristic for a placer that has to trade path length against vias: score each via as +25 mm of equivalent length on a 5 Gb/s channel.

### Gaps
- USB-IF primary documents (USB 3.2/USB4 specs, Type-C spec layout figures) and Intel platform design guides (PDGs) are not public or were not readable. No primary USB4 PCB numbers (impedance, skew, loss per lane) were found.
- No primary numeric rule was found for SBU routing beyond "straight, short, protected", or for placing the orientation mux relative to the receptacle.

---

## 2. PCIe Gen3 / Gen4 / Gen5

### Takeaway
TI's PCIe Gen5 note gives the most usable numbers. Total budget is 23.5 / 28 / 36 dB (Gen3/4/5), of which 13 / 14 / 16 dB is allotted to a "9-inch system board trace with high-loss material". Per-inch loss tables at 8 and 16 GHz turn this budget into a length limit. The other numbers: intra-pair ≤5 mil, AC caps 75–220 nF (220 nF typical), the smallest cap package with a 100 % two-layer pad void, stubs <15 mil preferred (Gen5 physics limit ~51–54 mil), and GND stitching vias within 50 mil of each signal via. Sources conflict on AC-cap value range (TI 75–220 nF vs QorIQ datasheets 176–265 nF for Gen3), on cap placement (near RX/connector vs "near TX"), and on return-via distance (50 mil vs 200 mil).

### Cited Findings
- Loss budget table (TI SNLA426, June 2023), Gen3 / Gen4 / Gen5 in dB: CPU package 3.5 / 5 / 9.0; system-board trace (9-inch trace with high-loss material) 13 / 14 / 16; CEM connector 0.5 / 0.5 / 1.5; 4-in add-in card 6.5 / 8.5 / 9.5; **total system loss 23.5 / 28 / 36**; crosstalk mitigation negligible / <2 / 4–5; temperature/humidity loss – / – / 2–3. Eye after EQ: height 25 mV / 15±1.5 mV / 15±1.5 mV; width 0.3 UI (37.5 / 18.75 / 9.375 ps) — [TI SNLA426](https://www.ti.com/lit/pdf/snla426) [P]
- 1-inch differential insertion loss (SDD21) at 8 GHz / 16 GHz: Megtron 6 (Dk 3.4, Df 0.002) 0.189 / 0.336 dB; Rogers (3.48, 0.0037) 0.251 / 0.411; GETEK (4.1, 0.011) 0.548 / 1.017; Nelco 4000-6 (4.0, 0.012) 0.578 / 1.078; **FR4 (4.4, 0.014) 0.686 / 1.289**; tetrafunctional FR4 (4.1, 0.022) 0.961 / 1.844 — [TI SNLA426 Table 9-1](https://www.ti.com/lit/pdf/snla426) [P]
- NXP: at Gen4 a PCB trace may add 1–5 ps of jitter and 1.0–1.2 dB of loss per inch. Any mux/switch consumes budget — [NXP AN12864](https://www.nxp.com.cn/docs/en/application-note/AN12864.pdf) [S]
- Impedance: PCIe spec allows **70–100 Ω** differential; add-in cards require **85 Ω**. This does not apply to vias, AC-cap pads, connectors or cables. REFCLK is 100 Ω with ≤200 fs RMS random jitter — [TI SNLA426 §10](https://www.ti.com/lit/pdf/snla426) [P]. TI SoC tables use different targets: 100 Ω ±10 % (AM57xx, KeyStone) and 95 Ω ±5 % (AM65xx), with SE 51–60–69 Ω — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- Matching: intra-pair (P vs N) within **5 mil**. Lane-to-lane matching is not required ("typically up to 1 inch of difference", but SNLA426 §13 also says "keep inter-pair length less than 6 inches", an internal inconsistency). SoC tables: skew between all RX pairs ≤550 mil and TX pairs ≤550 mil (AM57xx/KeyStone), or 6 ns RX / 1.5 ns TX (AM65xx) — [TI SNLA426 §11–14](https://www.ti.com/lit/pdf/snla426) [P]; [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- Serpentine: avoid where possible; each serpentine segment ≥**3×W or 3×RPH**, whichever is larger — [TI SNLA426 §17](https://www.ti.com/lit/pdf/snla426) [P]
- Spacing/edges: route ≥**5×W or 5×RPH** (whichever is larger) from the edge of the reference plane and ≥**4×RPH** from plane voids. Pairs must not come within **4–5×RPH** of another pair after escape. Ground-signal-ground routing is recommended — [TI SNLA426 §18](https://www.ti.com/lit/pdf/snla426) [P]
- Layer changes: stitch reference GND planes with vias placed symmetrically **within 50 mil (1.27 mm)** center-to-center of the signal vias (Gen5 note). This conflicts with **200 mil (5.08 mm)** in TI's general guide and SLLA414A — [TI SNLA426 §19](https://www.ti.com/lit/pdf/snla426) [P]; [TI SPRAAR7J §2](https://www.ti.com/lit/pdf/spraar7) [P]
- Vias: TI recommends top/bottom routing only and backdrilling if vias are needed. Keep stubs <**15 mil**, backdrill longer ones. Physics bound for Gen5: 20/80 % edge 12 ps → ~29 GHz bandwidth → quarter-wave ≈**54 mil** on Megtron 6 and ≈**51 mil** on FR4, the absolute maximum unbackdrilled stub. Use the **10/20/40 mil drill/pad/antipad** rule as a starting point, optimize antipads by simulation, add as many GND stitches around the antipad as possible, prefer via-in-pad, and remove non-functional pads — [TI SNLA426 §21–24](https://www.ti.com/lit/pdf/snla426) [P]. SPRAAR7J device tables allow **0 vias** on PCIe traces for AM57xx/KeyStone but **2** for AM65xx — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- AC caps: PCIe TX must be AC-coupled; value **75–220 nF**, with **220 nF** typically used — [TI SNLA426 §25](https://www.ti.com/lit/pdf/snla426) [P]. Conflicting: NXP QorIQ datasheets quoted on NXP's forum give Gen2 CTX 75–200 nF and **Gen3 176–265 nF**; a forum reply says 220 nF is fine for Gen1–Gen3 — [NXP community thread](https://community.nxp.com/t5/Layerscape/PCIe-AC-coupling-capacitors-values/m-p/741140) [S]. (220 nF satisfies both ranges.)
- AC-cap placement: chip-to-chip → cap **as close to the RX as possible**; chip-to-connector (CEM slot or edge finger) → cap **as close to the edge finger/connector as possible**. Use the smallest package: the 0201 pad is 12 mil wide vs a 5–7 mil 85 Ω trace. Void the reference plane under the pads 100 %, two layers deep, with the void larger than the pad to cover body fringing — [TI SNLA426 §26](https://www.ti.com/lit/pdf/snla426) [P]. The earlier note quoted "AC caps near the TX end" from a secondary source; this is a conflict.
- Device max lengths (TI SoCs): PCIe total ≤**4700 mil (119.4 mm)** AM57xx; ≤**5500 mil (139.7 mm)** KeyStone II/K2G; ≤**4000 mil (101.6 mm)** AM65xx — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- Stripline vs microstrip conflict: SPRAAR7J "does not recommend stripline routing of the high-speed differential signals". SNLA426 says closely coupled stripline is "typically advised" for crosstalk at Gen5 (vias and antipads must then be designed carefully) — [TI SPRAAR7J §3.2](https://www.ti.com/lit/pdf/spraar7) [P]; [TI SNLA426 §4](https://www.ti.com/lit/pdf/snla426) [P]

#### Rule table: PCIe
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| PCIE-Z | Diff impedance | 85 Ω (add-in/CEM); 70–100 Ω allowed by spec; SoC tables 95–100 Ω | SNLA426, SPRAAR7J [P] | All gens | K + S |
| PCIE-SKEW | Intra-pair | ≤0.127 mm (5 mil) | SNLA426 [P] | | K: `skew within_diff_pairs` |
| PCIE-LANE | Lane-to-lane | not required; SoC limit e.g. ≤13.97 mm (550 mil) | SNLA426, SPRAAR7J [P] | | K: `skew` across lane group (only if device demands) |
| PCIE-BUDGET | Board trace loss budget | 13 / 14 / 16 dB (Gen3/4/5) incl. vias/caps | SNLA426 [P] | Root-complex to CEM | S: Σ(length × dB/in at Nyquist) + per-via/per-cap allowance ≤ budget |
| PCIE-STUB | Via stub | <0.38 mm (15 mil) preferred; hard max ≈1.3 mm (51–54 mil) at Gen5 | SNLA426 [P] | Through-via boards | G: stub = board thickness − signal-layer depth per via |
| PCIE-RV | GND return vias at layer change | within 1.27 mm (Gen5) or 5.08 mm (general) | SNLA426, SPRAAR7J [P] | | G: nearest GND via to each signal via |
| PCIE-ACV | AC cap value | 75–220 nF (TI) / 176–265 nF Gen3 (NXP): use 220 nF | SNLA426 [P]; NXP [S] | TX | M |
| PCIE-ACPOS | AC cap position | near RX (chip-chip) or near connector/edge finger | SNLA426 [P] | | G: path distance cap→RX pin or cap→connector pad below threshold |
| PCIE-ACPAD | Pad void | 100 %, 2 layers, larger than pad | SNLA426 [P] | | G: zone keep-out exists under pads on L2/L3 |
| PCIE-EDGE | Distance to reference-plane edge / voids | ≥max(5W, 5H) / ≥4H | SNLA426 [P] | | G: offset test against filled zone outlines on reference layer |
| PCIE-SERP | Serpentine segment length | ≥max(3W, 3H) | SNLA426 [P] | | G |

### Inferences
- [D] Max routable length from the budget: L_max ≈ (budget_dB − Σ via/cap/connector allowances) / loss_per_in(f_Nyquist). Example: Gen5 on FR4 with the full 16 dB → 16/1.289 ≈ 12.4 in before any via allowance; Gen4 on FR4 at 8 GHz → 14/0.686 ≈ 20 in. TI's own example allots the 13–16 dB to a 9 in high-loss trace, so the per-inch figures above are optimistic (they exclude roughness and vias). The rule pack should store the budget, the per-material dB/in table and per-feature allowances, not a fixed mm limit.
- The AC-cap placement conflict is resolved by SNLA426's explicit topology split (chip-to-chip vs chip-to-connector), which the earlier "near TX" advice does not make. Encode placement as a function of link topology.
- 220 nF satisfies both the TI (75–220 nF) and NXP (176–265 nF) ranges, so a BOM checker can flag values outside 176–220 nF as "verify".

### Gaps
- The PCI-SIG Base and CEM specifications (C_TX table, channel IL targets per form factor, M.2 budgets) were not accessible; Gen3+ cap range and form-factor budgets are therefore snippet-level.
- No per-via loss figure (dB per via at 8/16 GHz) from a primary source was found; it needs simulation.

---

## 3. DDR3 / DDR4 / LPDDR4

### Takeaway
DDR rules are controller-specific, and modern TI guides express them in picoseconds over named segments (lead-in, trunk, stub, termination). The two primary TI documents read here give complete tables. DDR3 (KeyStone, SPRABI1D) works in mils: fly-by ADDR/CMD/CTRL matched to CK within ±20 mil at each SDRAM, stubs <80 mil, data byte ±10 mil, DQS/CK pairs ±1 mil, 39 Ω to VTT at the last SDRAM within 500 mil, VREF trace ≥30 mil with ≥15 mil spacing. DDR4 and LPDDR4 (AM62x, SPRAD06C) work in ps: e.g., DDR4 DQS→DQ ≤2 ps, CK P/N ≤0.4 ps per segment, total CK→ADDR_CTRL ≤4 ps per SDRAM; LPDDR4 CK/ADDR ≤450 ps total, CK P/N ≤0.75 ps, via stub ≤20 mil (CA) / 40 mil (data). KiCad 10 can now check ps-based `length`/`skew` and pad-to-pad `fromTo()` segments natively.

### Cited Findings

#### DDR3 (TI KeyStone, SPRABI1D, Rev. Jul 2022)
- Impedance: **50 Ω ±5 %** SE on all point-to-point and fly-by nets; **100 Ω ±5 %** differential on DQS and CK pairs — [TI SPRABI1D §6.3](https://www.ti.com/lit/pdf/sprabi1) [P]
- Address/command and control fly-by groups: route the same path controller → each SDRAM in sequence → VTT termination. Length-match each net to the clock **within ±20 mil (0.51 mm)** to each SDRAM separately. Same number of vias in each matched segment. Stubs **<80 mil (2.03 mm)**, stub skew **±10 mil**. Route adjacent to a solid GND (or DVDD15) plane, on close layers to minimize via skew — [TI SPRABI1D](https://www.ti.com/lit/pdf/sprabi1) [P]
- Clock fly-by group: CK pairs length-matched controller → each SDRAM **within ±1 mil**; clock stubs **<40 mil (1.02 mm)**; AC VTT termination at the end; same via count per segment — [TI SPRABI1D](https://www.ti.com/lit/pdf/sprabi1) [P]
- Data groups (byte lanes): DQS pairs matched **±1 mil**; all nets in a byte **±10 mil (0.25 mm)**; ≤**2 vias** per net with equal count in the byte; one layer per byte lane; no mid-point vias; point-to-point with ODT and no VTT; bit swaps within a byte allowed — [TI SPRABI1D](https://www.ti.com/lit/pdf/sprabi1) [P]
- Spacing: center-to-center ≥**5 W** including serpentine. 4 W is allowed but "not appropriate for bus speeds over 1066 MT/s". All matching uses stripline-equivalent length (velocity compensation for microstrip) — [TI SPRABI1D](https://www.ti.com/lit/pdf/sprabi1) [P]
- Termination: each address/command net end-terminated with **39–42 Ω** (39 Ω 1 % preferred) to VTT = VDDQ/2 = 0.75 V, placed at the **last SDRAM**. Each trace to its termination ≤**500 mil (12.7 mm)**, and the far side of the resistor ties directly to the VTT rail. All termination parts 1 % — [TI SPRABI1D §6.2](https://www.ti.com/lit/pdf/sprabi1) [P]
- VREF: decouple at the SDRAMs with **0.01 µF + 0.1 µF at each Vref pin** and 0.1 µF at the source. Trace ≥**30 mil (0.76 mm)** wide and as short as possible. Keep ≥**15 mil (0.38 mm)** from all other nets, route on the top layer, isolated or shielded with ground. Vref tolerance ±1 % — [TI SPRABI1D](https://www.ti.com/lit/pdf/sprabi1) [P]
- VTT: regulator close to the SDRAM VTT pins. Use a VTT island on the component-side layer with ≥1 × 0.1 µF near each VTT SDRAM pin and ≥1 × **10–22 µF** bulk ceramic on the island — [TI SPRABI1D](https://www.ti.com/lit/pdf/sprabi1) [P]
- Write-leveling limit: theoretical **2500 ps**. DDR3-1333 example: max write-leveling skew <2135 ps (or <1385 ps with the half-period term), min >365 ps; assumes 180 ps/in propagation. Design for positive CK-minus-DQS skew — [TI SPRABI1D §6.3.1.9](https://www.ti.com/lit/pdf/sprabi1) [P]
- Other vendors (snippet level). Intel FPGA DDR3: DQ/DQS/DM within a byte ±**10 ps**; FPGAs cannot reliably deskew more than 20 ps; address/command to clock ±**20 ps** at each device. ISSI: ±10 ps ≈ ±50 mil within byte group. PCBWay blog: ±25 mil typical; stub <200 mil, ideally <100 mil — [Intel DDR3 layout guidelines](https://www.intel.com/content/www/us/en/docs/programmable/683385/17-0/layout-guidelines-for-ddr3-sdram-interfaces.html) [S]; [ISSI DDR3 layout guidelines](https://www.digikey.com/Site/Global/Layouts/DownloadPdf.ashx?pdfUrl=036C264570594B5589E336C3F96AB73F) [S]; [PCBWay DDR3 blog](https://www.pcbway.com/blog/PCB_Design_Layout/DDR3_PCB_Layout_and_Routing_Guide_Topology_Placement_and_Signal_Integrity_Tip_474c261e.html) [S]

#### DDR4 (TI AM62x/AM62Lx, SPRAD06C, Rev. Mar 2025)
- CK and ADDR_CTRL (Table 2-6). Segment names: A1+A2 = SoC to first SDRAM, A3 = between SDRAMs, AS = stub, AT = to termination. Limits: A1+A2 length ≤**500 ps**; A1+A2 ADDR_CTRL-to-CK skew ≤**3 ps**; A3 length ≤**125 ps**, skew ≤3 ps; AS length 5–17 ps, AS skew 1.3–3 ps; AT length ≤**75 ps**, AT skew ≤14 ps; CK P/N skew ≤**0.4 ps** per segment and ≤**0.8 ps** total to each SDRAM; total CK-to-ADDR_CTRL skew to each SDRAM ≤**4 ps**; ≤3 vias per trace; via count difference ≤1. Spacing: 4w to other DDR4, 3w within ADDR_CTRL, 2w allowed for ≤500 mil near endpoints. Rcp = Zo ±1 Ω; Rtt = Zo ±5 Ω. Source (series) termination is **not allowed** — [TI SPRAD06C](https://www.ti.com/lit/pdf/sprad06) [P]
- Data group (Table 2-7): BYTE length ≤**500 ps**; DQS P/N skew ≤**0.4 ps**; DQS-to-DQ skew ≤**2 ps**; ≤2 vias, count difference 0; spacing 4w to other DDR4, 3w within byte. Match only within a byte; matching across bytes is "neither required nor recommended". Byte-lane swaps allowed; bit swaps within a byte allowed only without CRC — [TI SPRAD06C](https://www.ti.com/lit/pdf/sprad06) [P]
- Unit convention: "1 ps can be equated to 5 mils" of stripline-equivalent length, with velocity compensation for microstrip segments. Count vias individually from the processor to each SDRAM — [TI SPRAD06C Table 2-6 notes](https://www.ti.com/lit/pdf/sprad06) [P]
- VREFCA: nominal **20 mil** trace with 0.1 µF bypass near each device pin (may narrow briefly near endpoints). VREFDQ is internal. Without a VTT supply, generate VREFCA with a 1 % divider. VTT is routed as a power sub-plane at the end of the address/control bus, decoupled near the terminators. VTT is optional with a single memory device, but CK termination is still required — [TI SPRAD06C §2.11–2.12](https://www.ti.com/lit/pdf/sprad06) [P]

#### LPDDR4 (TI AM62x, SPRAD06C Tables 3-6/3-7)
- CK0/ADDR_CTRL: propagation delay ≤**450 ps** each (assumes Dk ≈ 3.7–3.9, Df ≈ 0.002); CK0 P/N skew ≤**0.75 ps**; ADDR_CTRL relative to CK0 within **±312.5 ps** (die pad to DRAM pin, including SoC package delay); ≤3 vias; via stub ≤**20 mil**; via count difference ≤1; spacing 5w to other LPDDR4 and to non-DDR nets, 3w within ADDR_CTRL — [TI SPRAD06C](https://www.ti.com/lit/pdf/sprad06) [P]
- Data: DQS and BYTE delay ≤450 ps each; CK0 delay minus each DQS delay = **0 to 3 tCK** (CK must be longer than DQS); DQS P/N ≤**1.5 ps**; DQS-to-BYTE skew ≤**150 ps** (per-bit deskew in the PHY loosens the budget); shortest DQ/DM minus DQS ≥**−49 ps**; ≤2 vias; via stub ≤**40 mil**; via count difference 0; spacing 5w between classes and bytes, 3w within. TI recommends initially matching in the layout tool to **<20 % of each limit**, then confirming by power-aware IBIS simulation across PVT — [TI SPRAD06C](https://www.ti.com/lit/pdf/sprad06) [P]
- Other TI SoC (from the earlier note, Jacinto 7): CK/CA propagation ≤300 ps, CK skew ≤0.75 ps — [TI SPRACN9](https://www.ti.com/lit/pdf/spracn9) (earlier note)

#### Rule table: DDR
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| DDR3-FLY | ADDR/CMD/CTRL vs CK per SDRAM | ±0.51 mm (20 mil); stub <2.03 mm, stub skew ±0.25 mm | SPRABI1D [P] | KeyStone DDR3 (default for DDR3) | K: `skew` with `fromTo('U_soc-*','U_dramN-*')` per SDRAM; G: stub length |
| DDR3-CK | CK pair match / stub | ±0.025 mm (1 mil) / <1.02 mm | SPRABI1D [P] | | K |
| DDR3-BYTE | Byte lane match | DQS ±1 mil, DQ/DM ±0.25 mm; ≤2 vias equal; one layer; no mid vias | SPRABI1D [P] | | K: `skew`, `via_count`; G: same-layer check |
| DDR3-TERM | VTT termination | 39 Ω 1 % at last SDRAM, trace ≤12.7 mm | SPRABI1D [P] | | G: pad distance last-DRAM-pin → R pad |
| DDR3-VREF | VREF routing | ≥0.76 mm wide; ≥0.38 mm to other nets; 0.01 + 0.1 µF at each pin | SPRABI1D [P] | | K: `track_width`, `clearance`; G: cap-to-pin distance |
| DDR-SP | Spacing | ≥5 W (DDR3 > 1066 MT/s); DDR4 4w/3w; LPDDR4 5w/3w; 2w allowed ≤12.7 mm near endpoints | SPRABI1D, SPRAD06C [P] | | K: `clearance` per class (center-to-center → edge gap = (k−1)·W) |
| DDR4-SEG | Segment delays | A1+A2 ≤500 ps; A3 ≤125 ps; AT ≤75 ps; AS 5–17 ps | SPRAD06C [P] | AM62x DDR4 | K: `length (max 500ps)` with `fromTo()` segments |
| DDR4-SKEW | Skews | CK P/N ≤0.4 ps/segment; CK↔ADDR ≤4 ps total; DQS↔DQ ≤2 ps | SPRAD06C [P] | | K: `skew (max …ps)` |
| LP4-DLY | Total delay | CK/CA/DQS/BYTE ≤450 ps; CK−DQS 0–3 tCK | SPRAD06C [P] | AM62x LPDDR4 | K (time domain) + S |
| LP4-STUB | Via stub | CA ≤0.51 mm (20 mil); data ≤1.02 mm (40 mil) | SPRAD06C [P] | | G: per-via stub length from stackup |
| DDR-XBYTE | No cross-byte matching | — | SPRAD06C [P] | DDR4/LPDDR4 | Rule-pack: do not emit cross-byte skew constraints |

### Inferences
- A KiCad rule generator for DDR should emit **one `fromTo()` rule per SDRAM per group** (ADDR/CMD to CK at each DRAM), plus `within_diff_pairs` skew for CK/DQS, rather than a single net-class skew. A single net-class skew cannot express fly-by "per-SDRAM" matching.
- TI's own advice to target <20 % of each limit in the layout tool (because tool delay models are simplified) is a sensible default derating factor for any ps-based rule an LLM emits.
- DDR3 vendor tolerances differ by roughly 2× (TI ±20 mil vs Intel ±20 ps ≈ ±120 mil vs PCBWay ±25 mil). The generator must not mix vendor packs; it should pick the controller vendor's pack and fall back to the tightest when the vendor is unknown.

### Gaps
- No JEDEC primary document was read. VREF/VTT numbers come from TI only.
- No primary DDR3 numbers from NXP i.MX or ST STM32MP guides were extracted this session. ST AN5122 and the Intel/ISSI pages surfaced only as snippets.

---

## 4. Ethernet 10/100/1000BASE-T (MDI, magnetics, PHY placement, Bob Smith)

### Takeaway
The two primary vendor guides agree on 100 Ω ±10 % MDI pairs, few vias (≤2 per trace), a void under the magnetics, and a chassis island. Numeric limits are MDI ≤2 in total (TI) or ≤4 in PHY→RJ45 (Microchip); intra-pair match 20 mil (1G) / 50 mil (10/100) (TI) or <50 mil (Microchip); inter-pair <600 mil (Microchip); pair-to-pair ≥30 mil (TI) or ≥0.3 in (Microchip); PHY→magnetics <1 in (max 3 in) and magnetics→RJ45 <1 in (Microchip); Bob Smith 75 Ω + 1000 pF/3 kV (or 1500 pF/2 kV) with ≥50 mil clearance around that cap; earth/chassis isolated by ≥20 mil on all layers and bridged by a cap plus ≥1 MΩ. ESD placement conflicts: the Ethernet-specific TI note puts protection on the PHY side of the magnetics.

### Cited Findings
- TI SNLA387 (June 2021): total MDI trace length **<2 in (2000 mil)**; length-match within **20 mil** (1G) and **50 mil** (10/100); minimize vias and stubs; **100 Ω ±10 %** differential. MII: total <6 in, matched 20/50 mil, 50 Ω ±10 %. Separate different differential pairs by ≥**30 mil** — [TI SNLA387](https://www.ti.com/lit/pdf/snla387) [P]
- TI SNLA387: continuous ground under MDI traces, voided **only** under in-line components (magnetics, chokes, AC caps, ESD diodes). Two-layer void (component layer + layer below) recommended for standard applications; all-layer void recommended for automotive. Void edge about **20 mil** beyond the component edge. No metal under the magnetics on any layer (an integrated-magnetics RJ45 is exempt). Place GND return vias close to signal vias. Earth ground isolated by ≥**20 mil keep-out on all layers**, connected to circuit ground only through a capacitor and a resistor of ≥**1 MΩ** — [TI SNLA387](https://www.ti.com/lit/pdf/snla387) [P]
- TI SNLA387 on ESD: TI's general ESD note and its Ethernet-specific ESD note disagree on placement. The Ethernet note puts the protection device on the **PHY side** of the magnetics, because large common-mode swings on the connector side can destroy the TVS during non-ESD events — [TI SNLA387](https://www.ti.com/lit/pdf/snla387) [P]. This conflicts with the generic connector-side rule in [TI SLVA680A](https://www.ti.com/lit/pdf/slva680) [P].
- Microchip AN2054 (Gigabit Ethernet Design Guide): 100 Ω controlled pairs. Intra-pair skew device→RJ45 <**50 mil**; inter-pair <**600 mil**. Minimize vias, matched on both traces; "a reasonable budget is two per differential trace". PHY→magnetics **<1 in**, and if unachievable no more than **3 in**. Magnetics→RJ45 <**1 in**. Overall differential-pair length device→RJ45 <**4 in**. Keep other signals ≥**0.3 in (7.6 mm)** from the pairs and pairs ≥0.3 in from each other except at the PHY, magnetics and RJ45 — [Microchip AN2054](https://ww1.microchip.com/downloads/en/Appnotes/00002054A.pdf) [P]
- Microchip AN2054, isolation/EMI: Bob Smith termination through **75 Ω** and **1000 pF** to chassis, cap rated **3 kV**; alternatives 1500 pF/2 kV or 1000 pF/3 kV EFT cap; keep ≥**50 mil** spacing from that capacitor to traces and components. With discrete magnetics, clear all planes from **halfway through the magnetics to the RJ45** so that only TRx pairs run there (high-voltage barrier); not required for integrated magnetics. Make chassis ground an isolated island with a void to circuit ground, with 2–3 **1206** pads across the void for experimental bridging. RJ45 shield to chassis. A separate chassis plane is required. Bypass caps: pad-to-via <**10 mil**, two vias on capacitor grounds. Crystal ±50 ppm with matched trace lengths — [Microchip AN2054](https://ww1.microchip.com/downloads/en/Appnotes/00002054A.pdf) [P]
- TI forum on DP83867: there is no MDI length maximum, but keep PHY→RJ45 ≲**3 in**. Match lengths within each pair and across all four pairs — [TI E2E DP83867IR](https://e2e.ti.com/support/interface-group/interface/f/interface-forum/774556/dp83867ir-max-distance-between-magnetics-and-phy) [S]
- Conflict with the earlier note: Pulse was cited there as saying the PHY should be separated from the magnetics by ≥25 mm (~1 in), whereas Microchip says PHY→magnetics **<1 in**. One reads as a minimum and the other as a maximum. The Pulse PDF was not re-read here — [Pulse layout considerations (earlier note)](https://www.mouser.com/pdfDocs/pulse_layout_considerations_final.pdf); [Microchip AN2054](https://ww1.microchip.com/downloads/en/Appnotes/00002054A.pdf) [P]

#### Rule table: Ethernet
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| ETH-Z | MDI impedance | 100 Ω ±10 % | SNLA387, AN2054 [P] | 10/100/1000BASE-T | K + S |
| ETH-LEN | MDI length | ≤50.8 mm (TI) / ≤101.6 mm PHY→RJ45 (Microchip) | SNLA387, AN2054 [P] | | K: `length` with `fromTo(PHY, RJ45)` |
| ETH-SKEW | Intra-pair / inter-pair | 0.51 mm (1G) / 1.27 mm (10/100); inter-pair <15.2 mm | SNLA387, AN2054 [P] | | K: `skew within_diff_pairs`; `skew` across 4 pairs |
| ETH-VIA | Vias | ≤2 per trace, matched | AN2054 [P] | | K: `via_count (max 2)` |
| ETH-SP | Pair-to-pair / to other signals | ≥0.76 mm (TI) or ≥7.6 mm (Microchip, outside endpoints) | SNLA387, AN2054 [P] | | K: `clearance` |
| ETH-PLC | PHY→magnetics, magnetics→RJ45 | <25.4 mm (max 76.2 mm) / <25.4 mm | AN2054 [P] (Pulse conflict) | Discrete magnetics | G: pad-to-pad centroid distance |
| ETH-VOID | Plane void under magnetics/chokes/ESD/AC caps | 2 layers (all layers for automotive); void edge ≈0.51 mm past part; HV barrier from mid-magnetics to RJ45 | SNLA387, AN2054 [P] | | G: zone keep-out polygons on L1–L2 (and all for automotive) |
| ETH-BOB | Bob Smith network | 75 Ω per center tap + 1000 pF/3 kV (or 1500 pF/2 kV) to chassis; ≥1.27 mm around HV cap | AN2054 [P] | Discrete magnetics | M (values/ratings); K: `clearance` around HV cap |
| ETH-CHAS | Chassis/earth isolation | ≥0.51 mm keep-out all layers; bridge = cap + ≥1 MΩ | SNLA387 [P] | Shielded RJ45 | K: `clearance` between GND and CHASSIS nets on all layers |
| ETH-ESD | ESD location | PHY side of magnetics (TI Ethernet note) vs connector side (generic) | SNLA387 vs SLVA680A [P] | | Vendor switch in pack |

### Inferences
- The Ethernet pack needs a topology parameter (discrete vs integrated magnetics, automotive vs standard), because the plane void and HV-barrier rules flip on it.
- For placement, the binding geometric constraints are the PHY→magnetics and magnetics→RJ45 distances plus the HV-barrier void. Routing constraints come second.

### Gaps
- No IEEE 802.3 primary text on isolation creepage at the PCB level was read. The Microchip line on isolation voltage did not extract cleanly and is omitted.
- No primary data reconciles the Pulse "≥25 mm" statement with Microchip's "<1 in".

---

## 5. HDMI, DisplayPort, MIPI CSI-2/DSI (D-PHY), SATA

### Takeaway
HDMI TMDS is 100 Ω ±15 % with no AC caps; the source skew budget is 0.15 Tbit intra-pair and 0.20 Tcharacter inter-pair. TI SoC tables add ≤4000 mil, 0 vias and ≤5 mil intra-pair. DisplayPort is 100 Ω ±10 % with 75–200 nF caps on main link and AUX and ≤20 ps intra-pair (~5 mil). MIPI CSI on TI AM62x allows up to 10 in, 85–115 Ω loosely coupled pairs, lane skew ≤40 ps and ≤2 vias. SATA is 85–115 Ω (100 nominal) with 10 nF AC caps (0.3–12 nF) on both TX and RX, ≤3500–5500 mil, ≤5 mil skew and no polarity inversion.

### Cited Findings
- HDMI (TI SLLA414A table): HDMI 1.4b clock up to 340 MHz and data up to 1.7 GHz; HDMI 2.0b data up to 3 GHz; HDMI 2.1b data up to 6 GHz. **No AC caps allowed**; no polarity reversal. Source intra-pair skew ≤**0.15 × Tbit**, inter-pair ≤**0.20 × Tcharacter**. **100 Ω ±15 %** diff, 50 Ω ±15 % SE — [TI SLLA414A](https://www.ti.com/lit/pdf/slla414) [P]
- HDMI (TI SPRAAR7J, AM57xx table): TMDS 90–100–110 Ω; total ≤**4000 mil (101.6 mm)**; intra-pair ≤5 mil; **0 vias** per TMDS trace — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- DisplayPort (TI SLLA414A): DP 1.2 5.4 Gb/s, DP 1.4 8.1 Gb/s, DP 2.1 UHBR10/13.5/20. AC caps required. Source intra-pair skew ≤**20 ps** ("TI recommends about 5 mils"). **100 Ω ±10 %** diff, 50 Ω ±15 % SE — [TI SLLA414A](https://www.ti.com/lit/pdf/slla414) [P]
- DisplayPort AC caps **75–200 nF** on main link and AUX (TI SN75DP126 datasheet; Diodes PI3VDP12412 note citing the DP 1.2 standard). Passives in the path sit next to each other. 0402 or smaller preferred, 0603 acceptable, with symmetric breakout for both lines — [TI SN75DP126](https://www.ti.com/document-viewer/ja-jp/SN75DP126/datasheet/application_and_implementation) [S]; [Diodes AN341](https://www.diodes.com/assets/Part-Support-Files/PI3VDP12412/AN341.doc) [S]; [NXP AN10798](https://www.nxp.jp/docs/en/application-note/AN10798.pdf) [S]
- MIPI CSI (TI SPRAAR7J, AM62x tables): CSI total ≤**10 in**; pair 85–100–115 Ω; SE 50 Ω. Pairs "must be loosely coupled" because the lines also run single-ended low-power signaling. Intra-pair skew is set by the D-PHY mode-conversion S-parameters, with a general estimate of **UI/50** (UI = 400 ps at 1.25 GHz → 8 ps [D]). Lane skew ≤**40 ps** (0.1 UI). ≤2 vias per CSI trace; 0 stubs — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- SATA (TI SPRAAR7J): 85–100–115 Ω; total ≤**3500 mil (88.9 mm)** on AM57xx and ≤**5500 mil (139.7 mm)** on KeyStone II; intra-pair ≤5 mil; **0 vias** in TI's tables — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]
- SATA AC caps on **both TX and RX**: **0.3–12 nF, typ 10 nF**, package 0402 minimum / 0603 typical (TI TDA2 datasheet). NXP CBTL04083 note: 0402 or smaller preferred, 0603 acceptable, no C-packs, same value/package and symmetric placement in each pair. LattePanda carrier guide: caps within ~10 mm of the SATA connector; SATA pairs do not tolerate polarity inversion — [TI TDA2E datasheet](https://www.ti.com/document-viewer/TDA2E/datasheet/sata-interface-schematic-sprabp6-c001) [S]; [NXP AN11082](https://www.nxp.com.cn/docs/en/application-note/AN11082.pdf) [S]; [LattePanda SATA guide](https://docs.lattepanda.com/content/mu_edition/design_guide_sata/) [S]

#### Rule table: video, camera, storage
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| HDMI-Z | TMDS impedance | 100 Ω ±15 % (TI SoC: ±10 %) | SLLA414A, SPRAAR7J [P] | HDMI 1.4–2.1 | K + S |
| HDMI-SKEW | Intra / inter | ≤0.15 Tbit / ≤0.20 Tchar (e.g., 6 Gb/s → 25 ps [D]); TI ≤5 mil | SLLA414A, SPRAAR7J [P] | | K: `skew (max 25ps)` within pairs |
| HDMI-AC | No AC caps | — | SLLA414A [P] | | M |
| HDMI-VIA | Vias | 0 (TI SoC tables) | SPRAAR7J [P] | | K: `via_count (max 0)` |
| DP-ACV | AC caps | 75–200 nF, ML + AUX, 0402 | SN75DP126, Diodes [S] | DP source | M |
| DP-SKEW | Intra-pair | ≤20 ps (~0.127 mm) | SLLA414A [P] | | K |
| CSI-Z | Impedance / coupling | 85–115 Ω, loosely coupled | SPRAAR7J [P] | D-PHY | K + S |
| CSI-LEN | Length / lane skew / vias | ≤254 mm / ≤40 ps / ≤2 | SPRAAR7J [P] | AM62x (≤1.25 GHz) | K: `length`, `skew (max 40ps)`, `via_count` |
| SATA-ACV | AC caps | 10 nF (0.3–12 nF), TX and RX | TI TDA2 [S] | | M |
| SATA-LEN | Length / skew / vias | ≤88.9–139.7 mm / ≤0.127 mm / 0 | SPRAAR7J [P] | TI SoCs | K |
| SATA-POL | No P/N inversion | — | LattePanda [S] | | M/G: pin mapping check |

### Inferences
- Interfaces whose skew is specified as a fraction of UI (HDMI, D-PHY) should be stored in the pack as formulas in UI and resolved to ps at the configured data rate, then to mm through KiCad 10's per-layer delay model.
- "Loosely coupled" for D-PHY is the opposite of the USB/PCIe defaults. The pack must carry a `coupling: loose|tight` flag that changes the gap chosen by the router.

### Gaps
- The HDMI Forum, VESA DP and MIPI Alliance primary layout documents were not accessible. HDMI 2.1 FRL-specific PCB budgets were not found.

---

## 6. CAN, RS-485, I2C and SPI bus limits

### Takeaway
These buses are dominated by cable and bus-level numbers that a PCB tool can still check locally: 120 Ω termination only at the two physical bus ends (or split 2 × 60 Ω + 4.7 nF for CAN), stub-length limits computed from driver transition time (CAN: ≤1/3 of critical length, ISO 0.3 m at 1 Mb/s; RS-485: electrical length <1/10 of rise time), and the I2C rise-time/capacitance pair (1000/300/120 ns; 400/400/550 pF) that bounds the pull-up value and on-board bus capacitance. TVS placement follows the generic ESD rules in §1.

### Cited Findings
- CAN (TI SLLA270): ISO 11898 recommends 40 m at 1 Mb/s, max **30 nodes**, max unterminated stub **0.3 m** at 1 Mb/s, 120 Ω twisted pair, terminated at **both ends with 120 Ω**. Avoid putting the termination inside a node, because the bus loses termination if that node is unplugged. Suggested cable length vs rate: 40 m/1 Mb/s, 100 m/0.5, 200 m/0.25, 500 m/0.10, 1000 m/0.05. For buses >100 m: rate (Mb/s) × length (m) ≤ **50** — [TI SLLA270](https://www.ti.com/lit/pdf/slla270) [P]
- CAN termination: standard 120 Ω (1/4 W 5 % "generally acceptable"), or split termination of two **~60 Ω ±1 %** resistors with a center cap (typ **4.7 nF**, 3 dB at 1.1 Mb/s), optionally driven by the transceiver's Vsplit/Vref pin — [TI SLLA270 §4.5](https://www.ti.com/lit/pdf/slla270) [P]
- CAN stubs: keep stubs ≤**1/3 of the critical length**, where critical length is the point at which round-trip delay equals the transition time. Example: 50 ns transition and 5 ns/m line → critical length 5 m → stub ≤**1.67 m**; slope control (160 ns) raises it to ~5.3 m — [TI SLLA270 §4.8](https://www.ti.com/lit/pdf/slla270) [P]
- RS-485 (TI SLLA272D, Rev. May 2021): terminate the trunk with 120 Ω at each cable end (or 2 × 60 Ω low-pass in noisy environments). Stub electrical length < **1/10 of driver 10/90 rise time**, L_stub ≤ t_r · v · c / 10. Examples at 78 % velocity: 1 Mb/s / 100 ns → **7 ft**; 250 kb/s / 250 ns → 19 ft; 200 kb/s / 500 ns → 38 ft. External failsafe: two **523 Ω** bias resistors with 120 Ω terminations (5 V ±5 %). Standard load 32 UL, with failsafe biasing worth up to 20 UL. Rule of thumb length (m) × rate (b/s) < **10⁷**. PCB: keep both lines close and equidistant — [TI SLLA272D](https://www.ti.com/lit/pdf/slla272) [P]
- I2C (TI SLVA689A, Rev. Oct 2026): rise time max **1000 / 300 / 120 ns** and bus capacitance max **400 / 400 / 550 pF** for Standard / Fast / Fast-mode Plus. VOL ≤0.4 V at 3 mA (VCC > 2 V). R_P(min) = (VCC − VOL(max)) / IOL; R_P(max) = t_r / (0.8473 · C_b) — [TI SLVA689A](https://www.ti.com/lit/pdf/slva689) [P]
- SPI/QSPI: the numeric rules found earlier (Infineon ±30/±200/±1500 mil at 133 MHz) remain the only primary numbers — see [rules_highspeed_emi.md §4](./rules_highspeed_emi.md); [Infineon AN240090](https://www.infineon.com/assets/row/public/documents/10/42/infineon-an240090-design-and-layout-guide-for-cyrs17b-cyel17b-flash-quad-devices-applicationnotes-en.pdf)

#### Rule table: field buses and low-speed
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| CAN-TERM | Termination | 120 Ω at the 2 bus ends only, or 2 × 60 Ω ±1 % + 4.7 nF | SLLA270 [P] | HS-CAN | M: node role flag (end node vs mid node) |
| CAN-STUB | On-board stub from bus connector to transceiver | ≪0.3 m (1 Mb/s); ≤1/3 critical length | SLLA270 [P] | | K: `length` on CANH/CANL from connector to transceiver (board stub is mm-scale, so trivially met: flag only daisy-chain T-branches) |
| CAN-PAIR | CANH/CANL routed as a pair | 120 Ω diff (cable impedance) | SLLA270 [P] | | K: diff pair class |
| 485-STUB | Stub | <t_r·v·c/10 | SLLA272D [P] | | Calc + K: `length` |
| 485-FS | Failsafe bias | 2 × 523 Ω with 120 Ω (5 V) | SLLA272D [P] | Bus master / one node | M |
| I2C-RC | Pull-up range | R_P ∈ [(VCC−0.4)/3 mA, t_r/(0.8473·C_b)] | SLVA689A [P] | All I2C | M + G: estimate C_b from trace length (≈ pF/cm from stackup) + pin C |
| I2C-CB | Bus capacitance | ≤400 pF (Sm/Fm), ≤550 pF (Fm+) | SLVA689A [P] | | G/M: Σ pin C + trace C |
| BUS-TVS | TVS at connector | see ESD-PATH | SLVA680A [P] | CAN/RS-485/I2C off-board | G |

### Inferences
- For PCB-only checks the CAN/RS-485 stub limits are metres, so they matter only for daisy-chained connectors (two connectors on one node). The useful on-board check is "termination populated only when node role = end".
- The I2C pull-up check can be fully automated once trace capacitance per mm is estimated from the stackup, which closes a common real-world failure (over-long I2C traces with 10 kΩ pull-ups at 400 kHz).

### Gaps
- No primary numeric guidance was found for CAN/RS-485 TVS-to-connector distance beyond the generic SLVA680A topology rules. The NXP UM10204 (I2C spec) download was blocked; the I2C numbers come from TI's restatement.

---

## 7. Clocks and crystals

### Takeaway
Only one primary numeric placement distance was found: Microchip's dsPIC33AK data sheet limits the oscillator circuit to **≤12 mm (½ in)** from the oscillator pins, on the same side, with load caps next to the crystal. ST AN2867 (Rev 15) gives no distances, only qualitative rules (guard ring essential, dedicated local ground plane, short tracks). AVR186 gives typical parasitics (XIN–GND 1 pF, XOUT–GND 2 pF, XIN–XOUT 0.5 pF) that a placer can budget against. Vendors **conflict** on metal-can grounding (ST: do not tie the can to oscillator ground; TI and AVR: connect the housing to ground) and on copper under the crystal (Microchip/AVR/TI: ground area or clean ground under it; a TI clock-generator datasheet: cut ground and power planes under the crystal). No primary source gives a numeric separation from switching nodes.

### Cited Findings
- Microchip dsPIC33AK512MPS512 Family Data Sheet, "External Oscillator Layout Guidance": place the oscillator circuit on the **same side** as the device, close to the oscillator pins, **not exceeding one-half inch (12 mm)**. Load caps go next to the oscillator on the same side. Use a grounded copper pour around the circuit, routed directly to MCU ground, with **no signal or power traces inside the pour**. On two-sided boards avoid any traces on the opposite side under the crystal. For fine-pitch packages, tie broken guard sections to a mirrored ground layer — [Microchip dsPIC33AK data sheet, oscillator layout](https://onlinedocs.microchip.com/oxy/GUID-E48B4A26-F201-4F0A-BCBA-16461582816A-en-US-4/GUID-AA04B64F-3C38-4E1C-8B51-49DE3CFE2419.html) [P]
- AVR186 (Atmel/Microchip): typical parasitics **XTALin–GND 1 pF, XTALout–GND 2 pF, XTALin–XTALout 0.5 pF**. Keep them to an absolute minimum because they reduce gain margin. Route XTALin and XTALout as far apart as possible. Place the XTALin load cap first and closest to its pin. Use NPO/C0G caps. Put a ground area under the crystal, connected to the oscillator ground, and connect the crystal housing to ground. Use a guard ring on single-layer boards. Keep load-cap grounds clear of return currents from USB, RS-232, LIN, PWM and power lines — [AVR186](https://www.insidegadgets.com/wp-content/uploads/2013/02/Best-Practices-for-the-PCB-layout-of-oscillators.pdf) [P]
- TI SLAA322D (MSP430 32 kHz): traces as short as possible, and include trace capacitance in the load-cap calculation. Route XIN/XOUT apart. Keep crystal→CL1→CL2→crystal loop short and symmetric, with both cap grounds close together. Never route the ground connection between the caps or around the crystal. Guard ring of "clean ground" tied to AVSS with a short trace and to no other ground. On 2-layer boards no digital lines under the crystal on the opposite side; fill with clean ground tied to AVSS. Connect the crystal housing to ground — [TI SLAA322D](https://www.ti.com/lit/pdf/slaa322) [P]
- ST AN2867 Rev 15 (Oct 2021) §7.1: crystal as close as possible to the MCU; a grounded guard ring is "essential". Route high-frequency signals away. Use a dedicated oscillator ground plane underneath, distinct from the application ground and connected to the nearest MCU ground. A **metal-package crystal should not be connected to the oscillator ground**. Coat the board in humid environments. The worked "bad layout" examples cite too-long paths, asymmetric caps, coupling and **too many test points**. No numeric distances are given — [ST AN2867 Rev 15 (ECS mirror)](https://ecsxtal.com/store/pdf/stm32-microcontroller-application-note-092823.pdf) [P]
- ST AN2867 frequency sensitivity: with 45 ppm/pF pullability and 7 pF ±5 % caps, C_L shifts ±0.175 pF → **~7.8 ppm** (~0.7 s/day). For the 32 kHz LSE, choose low-pullability crystals with **C_L ≥6 pF** (7 pF as a compromise; 9–12.5 pF in noisy environments at a power cost) — [ST AN2867 Rev 15](https://ecsxtal.com/store/pdf/stm32-microcontroller-application-note-092823.pdf) [P]
- Conflict, copper under the crystal: TI's CDCE925 clock-generator datasheet suggests cutting ground and power planes under the crystal area (to cut parasitic C), and notes discrete caps may be needed to hit C_L. Microchip, AVR186 and SLAA322D call for ground under the crystal — [TI CDCE925 datasheet](https://www.ti.com/document-viewer/lit/html/SCAS847J/GUID-3FD01874-CDCB-4457-A26C-73DAE96B48CB) [S]
- High-speed separation: "Do not route high-speed traces under or near crystals, oscillators, clock signal generators, switching power regulators, mounting holes, magnetic devices…" (no number) — [TI SPRAAR7J §3.2](https://www.ti.com/lit/pdf/spraar7) [P]

#### Rule table: crystals
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| XTAL-DIST | Crystal + load caps to MCU osc pins | ≤12 mm (Microchip); "as close as possible" elsewhere | Microchip DS [P]; AN2867 [P] | MCU Pierce oscillators | G: max pad-to-pad distance (crystal pads, cap pads → OSC pins) |
| XTAL-SIDE | Same board side as MCU | — | Microchip DS [P] | | G: footprint layer equality |
| XTAL-CAP | Load caps adjacent; XIN cap first; C0G | — | AVR186 [P] | | G: cap–crystal pad distance minimal; M: dielectric |
| XTAL-PAR | Parasitic budget | XIN–GND ~1 pF, XOUT–GND ~2 pF, XIN–XOUT ~0.5 pF typical | AVR186 [P] | | G: estimate trace C from length and stackup; flag if > budget |
| XTAL-SEP | XIN/XOUT routed apart | — | AVR186, SLAA322D [P] | | G: min distance between XIN and XOUT traces ≥ k·W |
| XTAL-GUARD | Grounded guard ring/pour; no foreign nets inside or under (adjacent layer) | — | AN2867, Microchip, SLAA322D [P] | | G: keep-out polygon around oscillator group; K: rule area `disallow track` for non-osc nets |
| XTAL-CAN | Metal can grounding | vendor switch: ST "do not tie to osc ground" vs TI/AVR "connect to ground" | AN2867 vs SLAA322D/AVR186 [P] | | Pack parameter |
| XTAL-TP | Avoid test points on osc nets | — | AN2867 [P] | | G |
| XTAL-HS | No high-speed/switching nets near | no number | SPRAAR7J [P] | | G: keep-out ring (designer-set; heuristic) |

### Inferences
- The 12 mm bound is a maximum, not a target. An optimizer should minimize the crystal loop and treat 12 mm as a hard violation threshold.
- The AVR186 parasitic budget gives a physically grounded score: trace capacitance ≈ length × C′ (pF/mm, from the stackup solver), and the placer should keep the total well under ~1–2 pF per pin.

### Gaps
- Silicon Labs AN0016.x and Abracon layout notes were blocked (Access Denied), so their numbers are missing. No primary source gives a numeric clearance from switch nodes, inductors or high-speed pairs to crystal nets.

---

## 8. Switching regulators: numeric loop, switch-node and feedback guidance

### Takeaway
No vendor found states a universal "Cin within X mm" or a maximum hot-loop area. Primary TI and ADI documents do give calibrated physical numbers a rule engine can use. A lateral hot loop of ~20 mm² over an L2 ground image plane measured >1 nH. A vertical loop using L2 as the return (2 mm²) measured <500 pH and ~4 V less SW overshoot (TI SNVA803). At 5 A/ns, 2 nH costs 10 V of overshoot (TI SLYT682). A 10 × 10 cm test loop drops from 187 nH alone to 42 nH over a plane at 1.5 mm and 13 nH at 0.13 mm, so a next-layer plane gives >3× less inductance than a 1.6 mm 2-layer board (ADI AN-139). Other practical rules: 1 via per amp (SLYT614), 0.3 mm vias from small 0402/0603 Cin directly into L2, SW copper limited to the inductor pad plus the minimum connection, top-layer copper keep-out under the inductor, a 5-mil L1–L2 dielectric, and FB divider at the FB pin with the sense trace on a different layer from SW, separated by ground (especially when R_FB > 100 kΩ).

### Cited Findings
- TI SNVA803 (Hegarty, Sept 2019, LM5146-Q1 example): a single-sided discrete-FET buck with lateral switching loop had "a relatively high area of almost **20 mm²**". Even with an L2 ground image plane, loop inductance was "**greater than 1 nH**". Using L2 as the return directly under the top layer gave a vertical loop of **2 mm²**, and measured parasitic loop inductance "**less than 500 pH**" with negligible ringing. Peak SW overshoot was lower by **~4 V** than the improved lateral layout. Four **10 nF 0402/0603** input caps sit very close to the high-side drain, with their grounds tied to L2 through multiple **12 mil (0.3 mm)** vias. SW copper includes "just the pad of the inductor and the minimum area required to connect to the MOSFETs", shielded by ground copper. SW and BST routing is single-layer, so no high-dv/dt vias reach the bottom side. Output caps are split on both sides of the inductor — [TI SNVA803](https://www.ti.com/lit/pdf/snva803) [P]
- TI SLYT682 (AAJ, automotive buck EMI): commutation slew may exceed **5 A/ns**, so **2 nH → 10 V overshoot**. Use a continuous L2 shield plane as close to the loop as possible, e.g., specify a **5-mil core dielectric**. Avoid vias in the hot loop so that the noise current stays on top. Keep SW pour short and wide. A full ground plane under SW is recommended on multilayer boards. Keep a **top-layer copper keep-out under the inductor** to reduce SW→VOUT capacitive coupling — [TI SLYT682](https://www.ti.com/lit/pdf/slyt682) [P]
- ADI AN-139 Table 1 (10 cm × 10 cm loop, 27 MHz): single-layer open loop **187 nH**; plane at 1.5 mm, solid plate 42 nH (rectangular loop 53 nH); at 0.5 mm 23 nH; at 0.27 mm 21 nH; at 0.12–0.13 mm **13 nH**. "A solid plane on the next layer in a multilayer board (four layers or more) will have over **3× less inductance** than a normal 1.5 mm 2-layer board with a solid bottom plane, and over **14× less** over a single-layer board." A close inner shield cancels the hot-loop field much better than any shield more than **1 mm** away — [ADI AN-139 (mirror)](https://theengineer.markallengroup.com/production/content/uploads/2015/01/an139f.pdf) [P]; [ADI AN-139 page](https://www.analog.com/en/resources/app-notes/an-139.html)
- TI SLYT614 (five steps, TPS62130A): place and route Cin first, then the inductor and SW snubber, then Cout and VOS, then small-signal parts, then a single-point ground connection. Use **one via per amp** of current when the input/output must change layers. Keep all components on one side — [TI SLYT614](https://www.ti.com/lit/pdf/slyt614) [P]
- Feedback divider (TI datasheets): FB is a high-impedance node, so place the divider **close to the FB pin**, not at the load, to shorten the FB trace. Route the remote-sense trace away from SW, the inductor and VIN; preferably put it on a different layer with a ground plane separating it from the SW polygon. This matters most when **R_FB > 100 kΩ** — [TI LM5163 datasheet](https://www.ti.com.cn/document-viewer/cn/LM5163/datasheet/49-ZHCSKD6) [S]; [TI TPS560430-Q1 datasheet](https://www.ti.com/document-viewer/lit/html/SLUSDF5A/feedback-resistors-t4862777-8) [S]
- Low-authority loop-area target: "keep the VIN → CIN → high-side FET → GND loop under **10 mm²**" (blog, not vendor) — [Embedded Hardware Design](https://embeddedhardwaredesign.com/dc-dc-buck-converter-pcb-layout-design-guidelines/) [S]
- No vendor document read in this session gives a numeric Cin-to-pin distance ("within 1 mm"), numeric SW-to-sensitive-net clearance, or a numeric maximum SW copper area. Searches for such phrases returned only qualitative vendor text — [search summary: HS Electronik, PCBSync, DigiKey](https://hs-electronik.com/news/buck-converter-pcb-layout-hot-loops-feedback-guide) [S]

#### Rule table: switching regulators
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| SMPS-LOOP | Hot-loop geometric area (Cin+ → VIN pin/HS FET → LS FET/PGND → Cin−) | Reference points: ~20 mm² lateral → >1 nH; 2 mm² vertical → <0.5 nH. Proposed tiers: ≤2 mm² excellent, ≤10 mm² acceptable, >20 mm² fail [D] | SNVA803 [P]; blog [S] | Buck/boost/half-bridge | G: polygon from pad centroids along routed copper; report area and estimated L |
| SMPS-L2 | Unbroken GND plane on the layer directly below the hot loop; thin L1–L2 dielectric | ≤5 mil (0.127 mm) suggested; >3× L reduction vs 1.6 mm 2-layer | SLYT682, AN-139 [P] | ≥4 layers | G: zone coverage of loop polygon on L2; stackup dielectric check |
| SMPS-OVS | Overshoot budget | V_os ≈ L_loop × dI/dt (2 nH × 5 A/ns = 10 V) | SLYT682 [P] | | Calc from SMPS-LOOP estimate vs FET V_DS margin |
| SMPS-CIN | Small HF Cin (0402/0603, 10 nF–100 nF class) at the switch; GND straight into L2 with multiple 0.3 mm vias | — | SNVA803 [P] | | G: Cin pad-to-pin path length, via count/diameter at Cin GND pad |
| SMPS-VIA | Vias for power current | ≥1 via per A (input/output transitions) | SLYT614 [P] | | G: via count per power net transition vs I rating |
| SMPS-SW | SW copper area | inductor pad + minimum FET connection; no SW/BST vias to the far side | SNVA803, SLYT682 [P] | | G: SW net copper area vs (inductor pad area × k) |
| SMPS-LKO | Top-layer copper keep-out under inductor | — | SLYT682 [P] (conflicts noted in earlier file) | | G: zone keep-out under inductor body on L1 |
| SMPS-FB | FB divider at FB pin; sense trace on other layer, shielded by GND, away from SW/L/VIN | no vendor mm number | LM5163, TPS560430-Q1 [S] | All regulators; critical when R_FB > 100 kΩ | G: divider–FB pin distance (heuristic ≤3–5 mm, uncalibrated); layer and plane-shield test vs SW polygon |

### Inferences
- The loop-inductance numbers turn a vague "minimize the loop" into a scoreable objective. A placer can compute the loop polygon area and the dielectric height to L2, interpolate inductance from the AN-139 / SNVA803 anchors, and convert it to overshoot with V = L·dI/dt.
- Because vendors avoid numeric distances, the rule pack should carry an explicit `datasheet_override` slot for parts whose datasheet gives a recommended layout (common for integrated bucks), with the reference layout's measured loop area as the target.

### Gaps
- MPS, Rohm, Vicor and EPC primary notes with numeric loop inductances were not read (EPC and Würth PDFs were blocked). No vendor-specified Cin distance, SW-to-sensitive-net clearance or SW area limit was found.

---

## 9. Board-edge, plane-edge, return-via and stitching rules

### Takeaway
Plane-edge offsets: TI's general high-speed guide says **≥90 mil (2.29 mm)** from the reference-plane edge and ≥1.5 W from voids. TI's PCIe Gen5 note scales with geometry: **≥5 × max(W, H)** from the plane edge and ≥4 H from voids. Microchip says SuperSpeed traces should not be within **5 × W** of a plane edge or split. Return vias at layer transitions should sit within **200 mil** (general TI) or **50 mil** (Gen5 TI). The 20H power-plane pullback rule is not supported by measurements and should not be encoded as a default.

### Cited Findings
- TI SPRAAR7J §3.2 and SLLA414A: high-speed differential signals routed **≥90 mil (2.29 mm)** from the edge of the reference plane; at least **1.5 W** from voids in the reference plane (not applicable where SMD pads are intentionally voided). Package breakout within **0.25 in (6.35 mm)** of the package. Antipads as large as possible (**30 mil** "provides good performance"), with no non-functional pads. Stitching capacitors across unavoidable splits **≤1 µF**, placed as close as possible to the crossing — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]; [TI SLLA414A](https://www.ti.com/lit/pdf/slla414) [P]
- Return vias: when the GND reference changes, stitch both GND planes with vias placed symmetrically **within 200 mil (5.08 mm)** center-to-center of the signal transition vias, closer being better (SPRAAR7J, SLLA414A). The Gen5 note says **within 50 mil (1.27 mm)**, with "as many as possible" GND stitches around the antipad — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]; [TI SNLA426](https://www.ti.com/lit/pdf/snla426) [P]
- Plane-edge rule for Gen5: ≥5 × W or 5 × RPH from the reference-plane edge; ≥4 × RPH from voids; also do not route near the "edge of the board" — [TI SNLA426 §18](https://www.ti.com/lit/pdf/snla426) [P]
- Microchip AN26.2: SuperSpeed traces not within **5X trace width** of the reference-plane edge or of plane splits. Narrow ground floods must be terminated with a via at all corners and ends, and floods on different layers connected with multiple vias — [Microchip AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) [P]
- 20H rule: Hubing and Shim's measured boards showed better-contained near fields but **slightly higher** radiation with the 20H rule. A December 2023 LearnEMC "EMC Question of the Week" cites decades of papers in which following 20H can increase radiation, and lists it among debunked guidelines — [Hubing/Shim, 20-H Rule Modeling and Measurements](https://scholarsmine.mst.edu/faculty_work/1604) [S]; [LearnEMC QOTW 2023-12-25](https://learnemc.com/qotw-231225) [S]; [LearnEMC EMC design myths](https://www.learnemc.com/emc-design-myths) [S]
- No source was found for a "3H from plane edge" trace rule (search explicitly returned nothing) — [search: LearnEMC/NextPCB results](https://www.nextpcb.com/blog/three-principles-in-pcb-design) [S]

#### Rule table: edges and returns
| ID | Rule | Value | Source | Applicability | Auto-check |
|---|---|---|---|---|---|
| EDGE-PL | HS trace to reference-plane edge | ≥2.29 mm (TI general) or ≥5·max(W,H) (Gen5) or ≥5 W (Microchip SS) | SPRAAR7J, SNLA426, AN26.2 [P] | All ≥1 Gb/s pairs | G: offset of trace from filled-zone boundary on its reference layer (not `edge_clearance`, which only checks board edge) |
| EDGE-VOID | HS trace to plane void | ≥1.5 W (TI general) / ≥4 H (Gen5) | SPRAAR7J, SNLA426 [P] | | G |
| EDGE-RV | GND return via at layer change | ≤5.08 mm (general) / ≤1.27 mm (Gen5); symmetric | SPRAAR7J, SNLA426 [P] | Pair changes reference | G: nearest GND-net via to each signal via |
| EDGE-BRK | Breakout length from package | ≤6.35 mm | SPRAAR7J [P] | BGA HS escape | G |
| EDGE-SCAP | Stitching cap across split | ≤1 µF, at the crossing | SPRAAR7J [P] | Unavoidable split crossings | G: cap within distance of crossing point |
| EDGE-20H | 20H plane pullback | do **not** enforce by default | Hubing/Shim, LearnEMC [S] | | — |

### Inferences
- KiCad's `edge_clearance` constraint only measures to the board outline, not to a copper-pour boundary. The plane-edge rule must therefore be a geometric post-fill check (or approximated by a rule area that shrinks the routing keep-in by the offset).
- The return-via distance should be parameterized by data rate: 200 mil for ≤5 Gb/s class interfaces, 50 mil for PCIe Gen4/5-class. That matches the two TI documents' scopes.

### Gaps
- No primary source quantified via-stitching pitch specifically at layer transitions beyond the per-via return distance. Perimeter stitching pitch remains λ/20 by analogy (earlier file).

---

## 10. Mounting holes, fab capabilities (JLCPCB, PCBWay, OSH Park) and assembly spacing

### Takeaway
Official capability pages give these 1 oz minimums. JLCPCB: 4/4 mil trace/space on 1–2 layers, 3.5/3.5 mil multilayer; PTH annular ring 0.25 mm recommended on 2-layer and 0.20 mm on multilayer (absolute 0.18 / 0.15 mm); min via hole 0.15 mm (0.2 mm preferred); silkscreen line ≥0.15 mm and text height ≥1.0 mm; pad-to-silk 0.15 mm; copper ≥0.2 mm from routed edges and ≥0.4 mm from V-cuts. PCBWay standard: 4/4 mil, drill 0.15–6.0 mm (surcharge <0.2 mm), annular ring 0.15 mm, legend character width ≥0.15 mm and height ≥0.8 mm. OSH Park: 2-layer 6/6 mil, 10 mil drill, 5 mil annular ring, 15 mil edge keep-out; 4-layer 5/5 mil, 4 mil annular ring, 10 mil drill to inner copper; silkscreen 5 mil (3 mil for short features). Assembly-spacing and mounting-hole keep-outs have no authoritative public standard numbers; vendor and forum values are given and marked as such.

### Cited Findings

#### JLCPCB (official capabilities page, read this session)
- Trace/space (1 oz): **0.10/0.10 mm (4/4 mil)** on 1–2 layers; **0.09/0.09 mm (3.5/3.5 mil)** multilayer, 3 mil acceptable in BGA fan-outs. 2 oz: 0.16/0.16 mm (2-layer), 0.15/0.15 mm (multilayer). 2.5/3.5/4.5 oz (2-layer): 0.2/0.25/0.3 mm. Track width tolerance ±20 %. HDI extreme 3/3 mil (2.7/2.7 extreme) — [JLCPCB PCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities) [P]
- Drill: 0.15–6.3 mm (2-layer and multilayer); 0.1 mm microvias only for board thickness ≤1 mm with ENIG/OSP. Min via 0.15 mm hole / 0.25 mm diameter. Via diameter should be **0.1 mm (0.15 mm preferred) larger** than the hole. **Preferred min via hole 0.2 mm**. Via hole-to-hole 0.2 mm; pad hole-to-hole 0.45 mm. Plated slot tolerance +0.13/−0.08 mm, non-plated ±0.2 mm — [JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities) [P]
- Annular ring: PTH 2-layer 1 oz **recommended ≥0.25 mm, absolute 0.18 mm**; multilayer 1 oz **recommended ≥0.20 mm, absolute 0.15 mm**; 2 oz ≥0.254 mm. NPTH pad ring ≥0.45 mm — [JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities) [P]
- Clearances: pad-to-track 0.1 mm (0.09 mm locally at BGA); SMD pad-to-pad (different nets) 0.15 mm; min SMD pad 0.25 × 0.25 mm; via hole to track 0.2 mm; PTH to track 0.28 mm min / **0.35 mm recommended**; NPTH to track 0.2 mm; inner-layer via hole to copper 0.2 mm, PTH hole to copper 0.3 mm; BGA pad to trace ≥0.1 mm (0.09 mm multilayer), 0.2–0.25 mm BGA pads need ENIG. Solder-mask bridge min pad spacing 0.10 mm (green/red/yellow/blue/purple), 0.13 mm (black/white). Plugged vias ≤0.5 mm diameter, ≥0.35 mm from mask openings — [JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities) [P]
- Legend: min line width **≥0.15 mm**; min text height **40 mil (1.0 mm)**; width:height ratio 1:6; pad-to-silkscreen **0.15 mm** — [JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities) [P]
- Outline: copper ≥**0.2 mm** from routed edges and slots; ≥**0.4 mm** from V-cut edges; routed-edge tolerance ±0.2 mm (±0.1 mm high precision); V-cut tolerance ±0.4 mm (board ≥0.6 mm), 25° groove, min 2 mm between V-cuts (3 mm recommended). Mouse-bite panels: 1.6 or 2 mm board spacing. Min tooling edge 3 mm. For JLCPCB SMT use **5 mm tooling edges, 2 mm tooling holes and 1 mm fiducials centred 3.85 mm from the panel edges**. Castellated holes ≥0.5 mm, hole to board edge ≥1 mm, hole to hole ≥0.5 mm. Impedance control ±10 % standard, ±5 % on request — [JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities) [P]
- Assembly (official assembly capabilities page): min IC pin pitch **0.35 mm** (standard PCBA) / **0.40 mm** (economic); min BGA pitch 0.3 / 0.5 mm; 01005 supported; recommended max panel 250 × 250 mm; standard PCBA board 70 × 70 to 460 × 500 mm — [JLCPCB assembly capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities) [P]
- JLCPCB's SMD component-to-component spacing table could not be read (JavaScript-rendered; last updated 25 Jul 2023 per search). A JLCPCB support reply (dated) says component-to-outline clearance equals copper-to-outline: 0.2 mm (routed) / 0.4 mm (V-cut) — [JLCPCB SMD components minimum spacing](https://jlcpcb.com/help/article/smd-components-minimum-spacing) [S]; [EasyEDA forum reply](https://easyeda.com/forum/topic/How-close-can-SMD-components-be-to-the-edge-of-the-PCB-for-JLCPCB-to-assemble-them-2645b5a11aad4f169de4faa8f0857581) [S]

#### PCBWay (official capabilities page, standard PCB)
- Min trace **0.1 mm (4 mil)**, min spacing **0.1 mm (4 mil)**; drill (CNC) **0.15–6.0 mm**, with surcharge for holes <0.2 mm or >6 mm; min annular ring **0.15 mm (6 mil)** "for pads with vias in the middle"; finished hole tolerance PTH ±0.08 mm, NPTH ±0.05 mm. Legend: min character width **0.15 mm**, min character height **0.8 mm**, width:height ratio **1:5**. Min plated half-hole 0.4 mm. Panel: ≥1.6 mm between boards for break-routing, 0 for V-score. Advanced table: line-to-board-edge 0.25/0.20 mm (CNC milling, two capability columns); impedance tolerance ±10 % (±5 Ω at ≤50 Ω) — [PCBWay capabilities](https://www.pcbway.com/capabilities.html) [P]
- PCBWay's advanced page lists 2/2 mil minimum trace/space for part of a board only — [PCBWay advanced capabilities](https://www.pcbway.com/advanced-pcb-capabilities.html) [S]

#### OSH Park (official docs)
- 2-layer: 1 oz; trace spacing **6 mil**, trace width **6 mil**; annular ring **5 mil**; board-edge keep-out **15 mil (0.381 mm)** from nominal edge; min drill **10 mil (0.254 mm)**; min slot 20 mil; drill tolerance ±2.5 mil max; 5 mil recommended between holes; no blind/buried/filled vias; 1.6 mm nominal. Silkscreen min line **5 mil (0.127 mm)** recommended, 3 mil for short lines/text/graphics — [OSH Park 2 Layer](https://docs.oshpark.com/services/two-layer/) [P]
- 4-layer: trace/space **5/5 mil**; annular ring **4 mil**; edge keep-out 15 mil; plated drill to internal copper **10 mil**; min drill 10 mil. Stackup FR408HR: L1–L2 prepreg **7.87 mil (0.1999 mm)**, core 39 mil. EM528 alternate stackup used for some 2025–2026 runs — [OSH Park 4 Layer](https://docs.oshpark.com/services/four-layer/) [P]

#### Assembly spacing and mounting holes (no authoritative standard found)
- Component spacing (secondary): Cadence quotes 10–12 mil (0.25–0.3 mm) side-to-side minimums and 20–40 mil (0.5–1 mm) component-to-edge, more for tall or heavy parts. TI recommends ≥**0.508 mm** between land areas of adjacent components — [Cadence DFA guide](https://resources.pcb.cadence.com/i/1541046/25) [S]; [TI SPRAA99C](https://www.ti.com.cn/document-viewer/cn/lit/html/SPRAA99C/GUID-164C9D50-16B4-451B-AE9B-3579FEE28AA7) [S]. Earlier-file values (IPC-7351 courtyard 0.25 mm Level B; V-score ≥2 mm, MLCC 3–5 mm) still apply.
- Mounting holes: no published standard keep-out. Practical anchors: M3 socket-head cap screw head ≈**5.5 mm** diameter (recess example 6.5 mm). One KiCad user's practice is ~7 mm non-conductive clearance around a 3.2 mm hole. M3 pads of 6 mm, or 7.4 mm on 1.6 mm boards — [BestPCBs counterbore guide](https://www.bestpcbs.com/blog/?p=36814) [S]; [KiCad forum: mounting holes clearance](https://forum.kicad.info/t/mounting-holes-clearance/10316) [S]; [Hackaday.io log](https://hackaday.io/project/26823/log/67508) [S]. TI: do not route high-speed traces near mounting holes — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]

#### Rule table: fab and assembly profiles (KiCad DRC minimums; design to "recommended")
| Parameter | JLCPCB 2L (rec / abs) | JLCPCB ML (rec / abs) | PCBWay std | OSH Park 2L | OSH Park 4L | KiCad check |
|---|---|---|---|---|---|---|
| Trace / space (1 oz) | 0.10 / 0.10 mm | 0.09 / 0.09 mm | 0.10 / 0.10 mm | 0.152 / 0.152 mm | 0.127 / 0.127 mm | K: `track_width`, `clearance` |
| Min drill | 0.2 pref / 0.15 mm | 0.2 pref / 0.15 mm | 0.15 mm (≥0.2 no surcharge) | 0.254 mm | 0.254 mm | K: `hole_size` |
| Annular ring | 0.25 / 0.18 mm | 0.20 / 0.15 mm | 0.15 mm | 0.127 mm | 0.102 mm | K: `annular_width` |
| Copper to routed edge | 0.2 mm | 0.2 mm | 0.20–0.25 mm | 0.381 mm | 0.381 mm | K: `edge_clearance` |
| Copper to V-cut | 0.4 mm | 0.4 mm | — | — | — | K: `edge_clearance` on V-cut layer |
| Hole to hole | 0.2 (via) / 0.45 (pad) mm | same | see table | 0.127 mm rec | 0.127 mm rec | K: `hole_to_hole` |
| Silk line width | ≥0.15 mm | ≥0.15 mm | ≥0.15 mm | 0.127 mm (0.076 short) | same | K: `text_thickness` |
| Silk text height | ≥1.0 mm | ≥1.0 mm | ≥0.8 mm | — | — | K: `text_height` |
| Pad-to-silk | 0.15 mm | 0.15 mm | — | — | — | K: `silk_clearance` |
| Mask bridge (min pad gap) | 0.10 mm (green) / 0.13 (black/white) | same | 4 mil-class (table) | — | — | K: `solder_mask_expansion` + DRC |
| Impedance tolerance | ±10 % (±5 % on request) | same | ±10 % (±5 Ω ≤50 Ω) | — | — | — |

### Inferences
- A fab profile should be a separate rule pack selected per order. Interface packs then layer on top (e.g., JLCPCB multilayer 0.09 mm minimum vs a USB3 pair that needs a solver-derived width). The pack should carry both `recommended` and `absolute` columns and let the router use `recommended` as `opt` and `absolute` as `min`.
- Silkscreen height differs (JLCPCB 1.0 mm vs PCBWay 0.8 mm), so an auto-generated reference-designator layer must be fab-aware.

### Gaps
- JLCPCB's component-to-component spacing table (JavaScript-rendered) and PCBWay assembly spacing were not readable. No standard mounting-hole keep-out exists in the sources found; the screw-head + tolerance derivation is the defensible method.

---

## 11. Implications for an LLM-driven KiCad placer/router

### Takeaway
The numbers above only become machine-actionable if every rule carries five things: (1) a match pattern that binds it to schematic objects (part class, pin function, net role); (2) typed parameters with units, including ps and formulas in UI or W/H; (3) provenance and precedence (datasheet > vendor family guide > interface default > generic), with conflicts recorded rather than silently resolved; (4) a check backend (KiCad DRU emission, geometric script, or simulation budget); and (5) a placement intent (anchor, adjacency, order along a path, keep-out) separate from routing constraints. KiCad 10's `fromTo()` path conditions and ps units make most DDR/SerDes rules natively checkable. Plane-edge offsets, loop areas, topology order and return-via distances still need geometric checks.

### Cited Findings
- KiCad 10 custom rules support `fromTo('RefDes-Pad','RefDes-Pad')` path conditions for `length`, `skew`, `track_width`, `clearance` and `diff_pair_gap`, with wildcards (e.g., `'U1-A*'`). `skew` supports `within_diff_pairs` — [KiCad 10.0 PCB Editor, custom rules](https://docs.kicad.org/10.0/en/pcbnew/pcbnew_advanced.html) [P, doc source]
- KiCad 10 time-domain tuning: `length`/`skew` constraints given in `ps` switch the tuner to propagation-delay mode, using per-layer unit delay and via delay. Example: `(constraint length (min 450ps) (opt 500ps) (max 550ps))`, `(constraint skew (max 5ps))`. Time and length units cannot be mixed within one constraint — [KiCad 10.0 PCB Editor, time-domain tuning](https://docs.kicad.org/10.0/en/pcbnew/pcbnew_editing.html) [P, doc source]
- TI recommends matching in the layout tool to <20 % of each ps limit because tool delay models are simplified — [TI SPRAD06C](https://www.ti.com/lit/pdf/sprad06) [P]

### Inferences

#### Proposed rule-pack schema (YAML)
```yaml
# rulepack schema v0 (proposal)
pack:
  id: <interface-or-circuit id>          # e.g. usb2_hs, buck_sync, xtal_pierce
  version: 0.1
  precedence: 30                          # 10 generic < 20 interface default < 30 vendor family < 40 device datasheet
  applies_when:                           # binding to the netlist / BOM
    parts: [ {role: <name>, match: {lib_regex: ..., pin_functions: [...], value_regex: ...}} ]
    nets:  [ {role: <name>, match: {pin: "<role>.<pin_function>"}} ]
  parameters:                             # typed, unit-carrying, overridable
    <name>: {value: <number|formula>, unit: mm|mil|ps|ohm|nF|pct|UI|W|H, tag: P|S|D, source: <url>, rev: <doc rev>}
  conflicts:                              # recorded, never silently resolved
    - {parameter: <name>, values: [{value: .., source: ..}, {value: .., source: ..}], resolution: <rule>}
  placement:                              # intents for the placer (soft scores or hard bounds)
    - {type: anchor|adjacent|order_along_path|max_distance|same_side|keepout_ring|orientation, ...}
  routing:
    netclasses: [...]
    diff_pairs: [...]
  checks:                                 # every rule names its backend
    - {id: <rule id>, backend: kicad_dru|geometric|simulation|bom, severity: error|warning|info, emit: <template or function name>}
```

Resolution policy: take the parameter from the highest-precedence pack that defines it. If two packs at the **same** precedence disagree, use the stricter value and raise an `info` finding citing both sources. Snippet-only values ([S]) never override primary values ([P]) at the same precedence.

#### Worked example 1: USB 2.0 HS device port
```yaml
pack:
  id: usb2_hs
  precedence: 20
  applies_when:
    parts:
      - {role: conn, match: {lib_regex: "USB_(A|B|C|Micro|Mini).*"}}
      - {role: phy,  match: {pin_functions: ["USB_DP","USB_DM"]}}
      - {role: esd,  match: {lib_regex: "(TPD|USBLC|PESD|ESD).*", optional: true}}
    nets:
      - {role: dp, match: {pin: "phy.USB_DP"}}
      - {role: dm, match: {pin: "phy.USB_DM"}}
  parameters:
    zdiff:           {value: 90,   unit: ohm, tol_pct: 15, tag: P, source: "https://www.ti.com/lit/pdf/slla414", rev: "SLLA414A 2026-01"}
    intra_skew_max:  {value: 1.27, unit: mm, tag: P, source: "https://www.ti.com/lit/pdf/spraar7", rev: "SPRAAR7J"}
    len_max:         {value: 304.8, unit: mm, tag: P, source: "https://www.ti.com/lit/pdf/spraar7"}   # TI AM57xx table
    len_warn:        {value: 150,  unit: mm, tag: P, source: "https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf"}
    via_max:         {value: 4,    unit: count, tag: P, source: "https://www.ti.com/lit/pdf/spraar7"}
    gap_other_min:   {value: 0.762, unit: mm, tag: P, source: "https://www.ti.com/lit/pdf/spraar7"}
    gap_clock_min:   {value: 1.27, unit: mm, tag: P, source: "https://www.ti.com/lit/pdf/spraar7"}
    esd_conn_max:    {value: 5.0,  unit: mm, tag: D, source: "heuristic; TI says 'as close as possible' (SLVA680A)"}
  conflicts:
    - {parameter: intra_skew_max, values: [{value: 1.27, source: SPRAAR7J}, {value: 3.81, source: SPRABT8A (S)}], resolution: stricter}
    - {parameter: len_max, values: [{value: 304.8, source: SPRAAR7J}, {value: ~101.6, source: Intel-derived (S)}], resolution: "warn at len_warn, error at len_max"}
  placement:
    - {type: order_along_path, path: [conn.DP, esd, phy.USB_DP], also: [conn.DM, esd, phy.USB_DM]}
    - {type: max_distance, a: esd, b: conn, value: esd_conn_max}
    - {type: anchor, part: conn, edge: board_edge}            # connector on the I/O edge
  routing:
    netclasses: [{name: USB2, nets: [dp, dm], width: from_stackup(zdiff), diff_gap: from_stackup(zdiff)}]
  checks:
    - {id: USB2-SKEW, backend: kicad_dru, emit: |
        (rule "USB2 intra-pair skew"
          (condition "A.hasNetclass('USB2')")
          (constraint skew (max 1.27mm) (within_diff_pairs)))}   # verify exact within_diff_pairs token form against the installed version
    - {id: USB2-VIA,  backend: kicad_dru, emit: |
        (rule "USB2 vias" (condition "A.hasNetclass('USB2')") (constraint via_count (max 4)))}
    - {id: USB2-LEN,  backend: kicad_dru, emit: |
        (rule "USB2 length" (condition "A.fromTo('${conn.ref}-*', '${phy.ref}-*') && A.hasNetclass('USB2')")
          (constraint length (max 304.8mm)))}
    - {id: USB2-SP,   backend: kicad_dru, emit: |
        (rule "USB2 to others" (condition "A.hasNetclass('USB2') && !B.hasNetclass('USB2')") (constraint clearance (min 0.762mm)))}
    - {id: USB2-STUB, backend: geometric, emit: no_t_junctions_or_testpoints(nets=[dp,dm])}
    - {id: ESD-PATH,  backend: geometric, emit: path_order_and_zero_vias(conn->esd)}
    - {id: USB2-AC,   backend: bom, emit: no_series_caps(nets=[dp,dm])}
```

#### Worked example 2: synchronous buck (integrated or discrete FETs)
```yaml
pack:
  id: buck_sync
  precedence: 20
  applies_when:
    parts:
      - {role: ic,   match: {pin_functions: ["VIN","SW","PGND|GND","FB"]}}
      - {role: cin_hf, match: {class: capacitor, nets_any: ["ic.VIN"], other_net: "ic.PGND", value_lt: "1uF"}, prefer_smallest_package: true}
      - {role: cin_bulk, match: {class: capacitor, nets_any: ["ic.VIN"], value_ge: "1uF"}, optional: true}
      - {role: ind,  match: {class: inductor, nets_any: ["ic.SW"]}}
      - {role: cout, match: {class: capacitor, nets_any: ["ind.!SW"], other_net: GND}}
      - {role: rfb_top, match: {class: resistor, nets_all: ["ic.FB", "VOUT"]}}
      - {role: rfb_bot, match: {class: resistor, nets_all: ["ic.FB", "GND|AGND"]}}
  parameters:
    loop_area_good:  {value: 2,   unit: mm2, tag: P, source: "https://www.ti.com/lit/pdf/snva803"}   # <0.5 nH measured
    loop_area_fail:  {value: 20,  unit: mm2, tag: P, source: "https://www.ti.com/lit/pdf/snva803"}   # >1 nH measured
    loop_area_warn:  {value: 10,  unit: mm2, tag: S, source: "https://embeddedhardwaredesign.com/dc-dc-buck-converter-pcb-layout-design-guidelines/"}
    didt:            {value: 5,   unit: A/ns, tag: P, source: "https://www.ti.com/lit/pdf/slyt682"}
    l1_l2_dielectric_max: {value: 0.127, unit: mm, tag: P, source: "https://www.ti.com/lit/pdf/slyt682"}
    vias_per_amp:    {value: 1,   unit: count/A, tag: P, source: "https://www.ti.com/lit/pdf/slyt614"}
    cin_gnd_via_dia: {value: 0.3, unit: mm, tag: P, source: "https://www.ti.com/lit/pdf/snva803"}
    fb_div_max_dist: {value: 4,   unit: mm, tag: D, source: "uncalibrated heuristic; vendors say 'close to FB pin'"}
  placement:                                   # SLYT614 order: Cin, L, Cout, small-signal, ground tie
    - {type: priority_order, parts: [cin_hf, ind, cout, rfb_top, rfb_bot]}
    - {type: same_side, parts: [ic, cin_hf, ind, cout]}
    - {type: max_loop_area, loop: [cin_hf.+, ic.VIN, ic.PGND, cin_hf.-], fail: loop_area_fail, warn: loop_area_warn, target: loop_area_good}
    - {type: max_distance, a: rfb_top, b: ic.FB, value: fb_div_max_dist}
    - {type: keepout_ring, around: ind, layers: [F.Cu], nets_disallowed: ["*"], except: [ind.pads]}   # SLYT682 top-layer keep-out under L
  routing:
    sw_copper: {max_area: "ind.pad_area + min_connection", vias_on_sw: 0}
    fb_trace:  {layer: "!= layer_of(SW)", shield: "GND plane between", keep_away_from: [SW, ind, VIN]}
  checks:
    - {id: SMPS-LOOP, backend: geometric, emit: loop_polygon_area_and_L_estimate(interp=[[187nH, 0, "single-layer"], [42nH, 1.5mm], [21nH, 0.27mm], [13nH, 0.13mm]])}   # AN-139 anchors (10x10 cm loop; use for ratios only)
    - {id: SMPS-OVS,  backend: geometric, emit: overshoot = L_est * didt; warn if > 0.2 * Vds_max}
    - {id: SMPS-L2,   backend: geometric, emit: zone_covers(loop_polygon, layer=next_inner, net=GND)}
    - {id: SMPS-VIA,  backend: geometric, emit: via_count(net=VIN|VOUT, at=layer_change) >= ceil(I_max * vias_per_amp)}
    - {id: SMPS-FB,   backend: geometric, emit: fb_layer_and_distance_checks}
  overrides:
    datasheet_reference_layout: {if_present: true, target_loop_area: measured_from_eval_board, precedence: 40}
```

#### Worked example 3: MCU Pierce crystal (HSE/LSE)
```yaml
pack:
  id: xtal_pierce
  precedence: 20
  applies_when:
    parts:
      - {role: mcu,  match: {pin_functions: ["OSC_IN|XTAL1|XIN", "OSC_OUT|XTAL2|XOUT"]}}
      - {role: xtal, match: {class: crystal}}
      - {role: cl1,  match: {class: capacitor, nets_all: ["mcu.OSC_IN", GND]}}
      - {role: cl2,  match: {class: capacitor, nets_all: ["mcu.OSC_OUT", GND]}}
  parameters:
    dist_max:       {value: 12,  unit: mm, tag: P, source: "https://onlinedocs.microchip.com/oxy/GUID-E48B4A26-F201-4F0A-BCBA-16461582816A-en-US-4/GUID-AA04B64F-3C38-4E1C-8B51-49DE3CFE2419.html"}
    c_par_xin_max:  {value: 1.0, unit: pF, tag: P, source: "https://www.insidegadgets.com/wp-content/uploads/2013/02/Best-Practices-for-the-PCB-layout-of-oscillators.pdf"}
    c_par_xout_max: {value: 2.0, unit: pF, tag: P, source: "AVR186 (typical values, used as budget)"}
    c_par_x2x_max:  {value: 0.5, unit: pF, tag: P, source: "AVR186"}
    hs_keepout:     {value: 3,   unit: mm, tag: D, source: "uncalibrated heuristic; SPRAAR7J gives no number"}
    metal_can_to_gnd: {value: vendor_switch, options: {st: false, ti: true, microchip_avr: true}, tag: P,
                       source: ["https://ecsxtal.com/store/pdf/stm32-microcontroller-application-note-092823.pdf", "https://www.ti.com/lit/pdf/slaa322"]}
  conflicts:
    - {parameter: copper_under_crystal, values: [{value: "ground pour", source: "Microchip DS, AVR186, SLAA322D"}, {value: "cut planes", source: "TI CDCE925 (S)"}], resolution: "ground pour for MCU Pierce; cut-plane variant only for clock-generator datasheets that ask for it"}
  placement:
    - {type: same_side, parts: [mcu, xtal, cl1, cl2]}
    - {type: max_distance, a: [xtal, cl1, cl2], b: [mcu.OSC_IN, mcu.OSC_OUT], value: dist_max, hard: true, objective: minimize}
    - {type: adjacent, a: cl1, b: xtal, order: "cl1 placed before cl2 (XIN side first)"}
    - {type: keepout_ring, around: [xtal, cl1, cl2, osc_traces], margin: hs_keepout, nets_disallowed: ["!osc_nets & !GND"], layers: [F.Cu, In1.Cu]}
  routing:
    guard: {type: gnd_pour_ring, tie: "single short connection to nearest MCU GND/VSS pin"}
    xin_xout_separation: {min: "3 * W", tag: D}
    testpoints_on_osc_nets: 0
  checks:
    - {id: XTAL-DIST,  backend: geometric, emit: max_pad_distance(group=[xtal,cl1,cl2], to=[mcu.OSC_IN,mcu.OSC_OUT]) <= dist_max}
    - {id: XTAL-PAR,   backend: geometric, emit: trace_capacitance(osc_nets, stackup) <= c_par_*}
    - {id: XTAL-GUARD, backend: kicad_dru, emit: |
        (rule "No foreign nets in crystal area"
          (condition "A.insideArea('XTAL_KEEPOUT') && !A.hasNetclass('OSC') && A.Net != 'GND'")
          (constraint disallow track via))}   # rule-area name generated per crystal; verify insideArea syntax for installed version
    - {id: XTAL-TP,    backend: geometric, emit: no_testpoints(osc_nets)}
```

#### Further design implications
- Every [D] heuristic (ESD ≤5 mm, FB ≤4 mm, crystal keep-out 3 mm, loop-area tiers) should ship with `tag: D` and default severity `warning`, so that it can be calibrated against vendor evaluation-board layouts before it is promoted to `error`.
- Delay-based packs (DDR, HDMI, D-PHY) should emit ps rules directly (KiCad 10 time domain) and apply TI's "<20 % of limit" derating as the `opt` target, with the full limit as `max`.
- Fab profiles (§10) should be packs with `precedence: 10` that set `min` values only; interface packs set `opt`/`max`. That separation prevents an interface pack from ever relaxing a fab minimum.

### Gaps
- The YAML schema is a proposal. It has not been validated against KiCad's exact S-expression parser for every constraint form (`within_diff_pairs` token form, `insideArea` vs rule-area names), which must be tested on the installed KiCad 10 build.
- The geometric backends (loop area, plane-edge offset, return-via distance, topology order) are specified as function names only. No existing open-source KiCad plugin implementing all of them was identified in this pass.
