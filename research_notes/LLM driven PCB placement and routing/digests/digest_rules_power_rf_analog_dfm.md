# Digest: rules for power conversion, PDN/decoupling, RF, analog and precision sensing, isolation, thermal, and DFM/fab, plus checkers and role detectors

**Sources digested**
- `rules_power_rf_analog_dfm.md`: read in full. Tag **RPA**; "§n" means its section n.
- `verification_rules.md`: the power, PDN, RF, analog, thermal, DFM and fab rows, plus its hard/soft classification. Tag **VR**. **Where VR and RPA conflict, VR wins**, and this digest uses the corrected values.
- `interface_rule_packs.md`: §7 crystals, §8 switching regulators, §9 edges and return vias, §10 fab, mounting holes and assembly, and §11 schema and worked examples. Tag **IRP**.

**Evidence tags**
- **[P]**: read in the primary document.
- **[P-sec]**: read in full, but the page is a secondary account.
- **[S]**: search snippet only.
- **[D]**: derived or computed by the note author.
- **(low)**: vendor blog or calculator.

**VR status words**
- VERIFIED: the number and its meaning match the source.
- +CTX: the number is right, but the catalog dropped a condition.
- CORRECTED: the source gives a different value, attribution or meaning.
- CONTESTED: primary sources disagree.
- NOT FOUND: absent from the primary documents read.
- NOT RETRIEVABLE: the source could not be fetched.

**Severity**
- S1: functional or safety failure.
- S2: EMI, thermal or performance failure.
- S3: yield or margin loss.
- S4: best practice.

---

## 0. Corrections and conflicts at a glance

| Item | Catalog (RPA) said | Corrected / status (VR, IRP) |
|---|---|---|
| Bootstrap sizing | C_boot ≈ 10× C_g; C_VDD ≈ 10× C_boot | **C_boot ≥ 10× C_g** (so it is depleted by no more than 10%); **C_VDD ≥ 10× C_boot**. CORRECTED ([TI SLUA887A p.3–4](https://www.ti.com/lit/pdf/slua887)) |
| IPC-2221B >500 V | +0.0025 mm/V (B1), +0.005 (B2/B4) | B1 0.0025, B2 0.005, B3 0.025, **B4 0.00305 mm/V**. CORRECTED ([EMA table](https://www.ema-eda.com/ema-resources/blog/pcb-clearance-and-creepage-distance-table/)) |
| JLCPCB silkscreen | text ≥0.8–1.0 mm (unverified) | **≥1.0 mm text, ≥0.15 mm stroke**, pad-to-silk 0.15 mm. CORRECTED ([JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities)) |
| u-blox via fence | GND vias ≤0.5 mm from coplanar edge, ≤2 mm pitch | **NOT FOUND** in NORA-B2, MAX-M5Q or LEA-6 manuals, which say only "add as many vias as possible". λ/20 is not primary either. |
| Espressif 15 mm | PCB antenna copper keep-out | **In-enclosure clearance.** The PCB keep-out comes from the module's keep-out figure. VERIFIED+CTX |
| RF↔SMPS 20 mm | Vendor heuristic | NOT FOUND. Primary sources are qualitative ("far from any noise source"). |
| Miter 50–60% | Optimal miter | NOT FOUND. Johnson (citing Edwards): rounding removes only 21% of corner copper; neutralising the excess capacitance takes removing 70–90%. ([Johnson](https://www.sigcon.com/Pubs/edn/bigbadbend.htm)) |
| LDO output caps "within ~2 mm" | MPS | The MPS <2 mm is for the **input** cap and VCC cap. **2 cm²/W NOT FOUND** in any primary source. |
| CIN–COUT ground proximity (PWR-08) | COUT GND within a few mm of CIN GND | CONTESTED. Rohm: **≥1–2 cm apart**. MPS/TI: close or common return. Drop it as a default. |
| Copper under inductor | TI vs blog | CONTESTED between **two primary vendors**. TI: top-layer keep-out with L2 GND kept. Rohm: no ground directly below (eddy currents lower L and raise loss). Hubing: a plane under some chokes or transformers is "not a good idea". |
| Thermal-via tenting | Tent ≥ via+0.1 mm | CONTESTED. TI SLOA122: "Do not cover the vias with solder mask". TI SLUA271 and Renesas TB389: tent from the top, mask 0.1 mm larger than the hole. |
| EP void limit | ≤25% (IPC-A-610 via pSemi) | TI: 25% is the point of diminishing returns, but **TI prefers a 50% limit** in high-power applications. +CTX |
| Fiducial edge distance | ≥5 mm | CORRECTED. On boards: SMEMA 7.62 mm + fiducial clearance. On panels: JLC puts 1 mm fiducials 3.85 mm from the edge on 5 mm rails. |
| Test-point clearance | ≥2.5 mm from parts | CORRECTED. **0.040" (1.0 mm)** to components; handlers may need up to 0.138" (3.5 mm); 0.125" from the board edge. |
| AMS-02 escape | "Unless the datasheet says otherwise" | ADI (Bryant, an MT-031 co-author) says connect AGND/DGND to analog ground "**even if the data sheet suggests otherwise**". Keep the escape only for multi-converter parts that specify their own scheme (AD5522). |
| Guard mask opening | No solder mask over guard | Not in AN-241. The pages that state it were NOT RETRIEVABLE. |
| SLVA959 via thermal R | 5.73 °C/W per via | **Error in the TI document.** Radii and an annulus were treated as solid copper. Use ~150–261 °C/W per via. |
| SLVA959 λ | 25 °C·cm/W | Typo. Its Eq. 3 uses 0.25, and the 71.4 °C/W result matches 0.25. |
| Via ampacity, 12 mil | 2.21 A (SLAA896) vs 0.84 A (SLVA959) | A 2.6× conflict. Use the conservative SLVA959/IPC-2152 value as the default. |
| PI AN-72 spark gap | — | 6.4 mm (5.5 mm acceptable) in the layout section vs "at least 5.4 mm" in the ESD section. The document is internally inconsistent. |
| u-blox NORA-B2 casing | — | ≥10 mm vs "minimum clearance of 5 mm" in another bullet. Internally inconsistent. |
| JLCPCB SMD pad spacing | ≥0.10 mm at 1 oz (RPA §6 [P]) | VR/IRP give SMD pad-to-pad (different nets) **0.15 mm** and pad-to-track 0.1 mm. These may be different parameters (mask-bridge pad spacing vs different-net spacing). **Re-check before encoding.** |

VR's meta-finding: the snippet-based catalog numbers were mostly right. Nearly every discrepancy was a **dropped applicability condition** (device family, enclosure vs PCB, a single measured part, E-field only), not a wrong value. So every rule record needs `applies_if` and `source_scope` fields (VR §1 Inferences).

---

## 1. Switching converters

### 1.1 Governing principle
Every source puts one rule first: find the loop that carries fully switched (pulsating, high-di/dt) current and make it physically as small as possible. Place it first, on one layer, with a solid plane directly underneath. AN-139 calls this the "hot loop" and the dominant EMI source. The on-cycle and off-cycle loops are not the ones to optimise. CIN sources all the AC currents, and they end at COUT ([AN-139 mirror](https://theengineer.markallengroup.com/production/content/uploads/2015/01/an139f.pdf) [P]).

After the hot loop, the ranking is:
1. small SW copper;
2. the inductor next to SW;
3. COUT;
4. FB taken by Kelvin connection at COUT and routed away from SW and L;
5. one quiet AGND tie.

Physics: V_spike = L·di/dt. At slew rates above 5 A/ns, 2 nH gives 10 V of overshoot ([TI SLYT682](https://www.ti.com/lit/pdf/slyt682) [P]). Another example: 1 nH × 1 A/ns = 1 V.

### 1.2 Hot-loop membership by topology (RPA §1 inference; consistent with AN-139 and SNVA731)
The hot loop is the set of branches whose current steps from 0 to I at each edge. Branches with continuous (triangular) current are not in it.

| Topology | Hot loop (place first, tightest) | Not hot | Notes |
|---|---|---|---|
| Buck | CIN_HF+ → HS switch / VIN pin → SW → LS switch or diode / PGND → CIN_HF− | L, COUT | For integrated parts: CIN_HF + PVIN + PGND. CIN_HF is the smallest-package ceramic. |
| Boost | LS switch (SW→PGND) → rectifier / HS (SW→VOUT) → COUT_HF → PGND | L, CIN | COUT_HF ground takes the shortest path to IC PGND ([SNVA731](https://www.ti.com/lit/an/snva731/snva731.pdf): "the most critical PCB feature") |
| Inverting buck-boost | CIN, switch, diode/sync FET and COUT in one series loop | L | Both caps are hot; put the CIN and COUT grounds side by side at the IC. |
| 4-switch buck-boost | Two loops: input half-bridge + CIN, output half-bridge + COUT | L | One HF cap per half-bridge, right at its FETs. |
| SEPIC/Ćuk | Switch → coupling cap → rectifier → COUT → GND → switch | L1, L2, CIN | Inference only. |
| Flyback | Primary (CIN→pri→FET→Rsense), clamp (pri→D→RC), secondary (sec→rect→COUT), bias winding | Output LC post-filter | Respect creepage (§5). |
| Half-bridge gate | Driver OUT → gate → Kelvin source → return; bootstrap C_BOOT↔HB/HS | — | The gate loop must not share the power-source inductance (EPC). |
| LDO | No switching loop | — | Thermal dominates. |

### 1.3 Measured loop inductance and plane proximity
- **AN-139 Table 1** (10×10 cm loop at 27 MHz) [P], VERIFIED:

  | Configuration | L |
  |---|---|
  | Single-layer open loop | 187 nH |
  | Inner-copper shorted loop | 141 nH |
  | Solid plate at 1.5 mm | 42 nH |
  | Rectangle at 1.5 mm, no overlap | 53 nH |
  | Plane at 0.5 mm | 23 nH |
  | Plane at 0.27 mm | 21 nH |
  | Plane at 0.12 mm (text says 0.13 mm) | **13 nH** |

  A next-layer plane on a ≥4-layer board gives ">3× less" inductance than a 1.5 mm 2-layer board with a bottom plane, and ">14× less" than a single-layer board. The mechanism is mirror eddy currents in the plane.
- **Second hot loop.** The INTVCC/driver decoupling loop carries roughly 20 dB less RF energy than the input-cap loop. Treat it as the second priority, with a solid plane on the next layer (AN-139; [Kueck Part 2](https://www.analog.com/media/en/technical-documentation/technical-articles/Kueck_Layout_power_supply_part_2.pdf)).
- **TI SNVA803** (LM5146-Q1) [P] ([SNVA803](https://www.ti.com/lit/pdf/snva803)):
  - A lateral loop of about 20 mm² is still above 1 nH, even over an L2 image plane.
  - A vertical loop using L2 as the return measures 2 mm² and <500 pH, with about 4 V less overshoot.
  - Four 10 nF 0402/0603 input caps sit at the HS drain, grounded to L2 through multiple 12 mil (0.3 mm) vias.
  - The SW polygon is the inductor pad plus the minimum FET connection; SW and BST are routed on one layer.
- **EPC** [P] ([WP010](https://epc-co.com/epc/Portals/0/epc/documents/papers/Optimizing%20PCB%20Layout%20with%20eGaN%20FETs.pdf); [presentation](https://epc-co.com/epc/Portals/0/epc/documents/presentations/High-Performance%20Layout%20Techniques%20to%20Maximize%20GaN%20Device%20Performance.pdf)):
  - Raising loop inductance from 0.4 to 2.9 nH costs more than 4% efficiency (1 MHz, 12→1.2 V).
  - At 1.6 nH, overshoot is 100% of V_in; at 0.4 nH it is 30%.
  - The "internal vertical" layout, called "optimal", uses the first inner layer as the return. It gives about 65% less inductance than the best conventional loop, and 0.8% and 1% full-load efficiency gains over the vertical and lateral loops.
  - A vertical loop's inductance rises by up to 80% when board thickness doubles from 31 to 62 mil.
  - For lateral loops, the shield-plane distance dominates: 4, 12 and 26 mil were tested, and 4 mil was best.
  - Benchmark loops: Si MOSFET about 2 nH, eGaN about 1 nH.
- **DTU** ([IAS 2020](https://orbit.dtu.dk/files/236953218/IAS_accepted_PCB_for_GaN_2020.pdf)) also prefers vertical loops on multilayer boards, but notes they are harder to characterise (via effects, inductive coupling).
- **TI SLYT682:** use a minimum-thickness dielectric to the shield, for example a 5-mil core, and no vias in the hot loop, so the noise current stays on the top layer.
- **Kueck** ([Part 1](https://www.analog.com/media/en/technical-documentation/technical-articles/kueck_layout_power_supply_part_1.pdf)) recommends ≥4 layers, because a 2-layer board's shield sits >1 mm away.
- **Exception (Hubing, VR):** supplies of 100 W or more "may require an isolated return". The single-layer-over-adjacent-plane advice "can be misleading" there ([LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines)).
- **Rule-pack tiers [D]** (IRP §8): ≤2 mm² excellent, ≤10 mm² acceptable, >20 mm² fail, anchored on SNVA803. The other thresholds found are a low-authority <10 mm² ([blog](https://embeddedhardwaredesign.com/dc-dc-buck-converter-pcb-layout-design-guidelines/) [S]) and 1 cm² for a boost ([Firgelli](https://www.firgelliauto.com/blogs/engineering-calculators/boost-converter-calculator), low). **No primary pass/fail loop-area limit exists** (VR §3 gaps). The YAML default `max_mm2: 15` in RPA is unsourced.

### 1.4 Placement order and the input capacitor
- **TI SLYT614** (5 steps) [P] ([SLYT614](https://www.ti.com/lit/an/slyt614/slyt614.pdf)), VERIFIED:
  1. CIN is the first part placed after the IC and is routed immediately ("as close to the IC as allowed by manufacturing rules"; "no vias").
  2. Inductor with minimum SW copper, plus the RC snubber if used.
  3. COUT and VOS. VOS is "the most critical small-signal connection".
  4. Small-signal parts. EN/PG are "the least important … do these last".
  5. A single-point ground to the system.

  Further SLYT614 points:
  - "Keep all components on a single side."
  - Put system vias "outside the circuit, versus between the input capacitor and IC".
  - Route quiet grounds directly back to the AGND pin rather than via'ing them into the system plane.
  - One via per amp, "more is better".
- **WCSP exception** (SLYT614 p.3–4, VR +CTX): when SW sits between VIN and PGND, route SW under the input cap. Vias in the SW-to-L path are "a better choice than moving the input capacitor".
- **The only numeric primary CIN distance:** MPS AN065 says "<2 mm distance from the Chip". The VCC cap is also <2 mm, on the same layer with no via ([MPS AN065](https://media.monolithicpower.com/document/PCB_Layout_Design_Guidelines_for_NB67xSeries.pdf) [P]).
- **Relative language from other vendors:** SLVA818 says "Every millimeter makes a difference!" ([SLVA818](https://www.ti.com/lit/pdf/slva818)). Rohm says "Shortening the wiring even by 1 mm is highly recommended."
- **Rohm** 60AN066E Rev.004 [P] ([Rohm](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf)):
  - CBYPASS is 0.1–0.47 µF X5R/X7R at the IC on the top layer; the bulk CIN may sit about 2 cm away.
  - Never move CBYPASS to the far side through vias ("operates as a reverse effect"). Never put the freewheel diode on the bottom through vias.
  - The inductor should be close to the IC, but there is "no need to be as close as input capacitor".
  - Via inductance: L ≈ (h/5)·(ln(4h/d)+1) nH (Johnson).
- **MPS** additionally:
  - VIN and PGND on ≥2 layers, using 10 mil drill / 20 mil pad vias.
  - 1–2 vias under each VIN and PGND pin on NB670/1, ≥3 on NB675; more than 20 vias between the two input caps.
  - ≥4 vias from the VCC cap to AGND and 8 to PGND (NB675).
  - ≥4 layers, with Inner1 used only for PGND.
- **AN-136** (Zhang) [P from mirror; VR could verify only via snippet] ([mirror](https://docs.ampnuts.ru/analog.com.datasheet/ltc3729l-6/related_data/an136f.pdf)):
  - Power stage first, small-signal after.
  - C_HF is a 0.1–10 µF low-ESL ceramic.
  - Power parts on one side and power traces on one layer. Change layers only in continuous-current paths, never in the hot loop, and with multiple vias.
  - Ground or DC planes go between the power layer and the small-signal layer: "always have a ground layer next to the outside power stage layer". Do not segment planes.
  - No thermal-relief pads or vias on power parts.
  - Keep each decoupling cap's +/− via pair close together.
  - The controller sits near VOUT+ (buck) or VIN+ (boost), away from the hot loop, with its decoupling directly at the pins and no vias.
  - In a multiphase example (PWChip summary [S]), one 1 µF HF input cap per channel kept switching waveforms stable to 30 A.
- **Boost** ([SLVA773](https://www.ti.com/lit/an/slva773/slva773.pdf) [P]):
  - Output cap close, with about one via per amp if vias are needed. A small cap can sit next to the IC with bulk farther out.
  - The input-cap ground goes close to PGND.
  - A large VIN copper area is acceptable because VIN is quiet.
  - CIN ground, COUT ground and IC ground "form a Power-Ground".
- **Renesas DA9080 PMIC** [P] ([AN](https://www.renesas.com/en/document/apn/da9080-pcb-layout-recommendations)):
  - Input caps on the device's layer.
  - L2 is the power-GND return, **with GND cuts between bucks** to limit ground bounce into the LDO. This is a vendor-mandated partition that conflicts with the one-ground doctrine.
  - Output current runs on the top layer without vias.

### 1.5 Switch node and inductor
- **Minimise SW copper.** "All copper connected to the SW node is one plate of a parasitic capacitor" (SLYT614). Rohm: an enlarged SW area "may work as an antenna". TI AAJ: a short, wide SW pour with a full ground plane under it. AN-136 adds that ground copper under SW gives extra shielding. VERIFIED, but no source gives a numeric area.
- **Width limit:** a SW trace wider than 100 mil (2.54 mm) adds capacitive loading ([TI LM10504](https://ti.com/document-viewer/LM10504/datasheet/layout) [P]).
- **SW copper on one layer only:** "Do not use multiple layers in parallel" for the SW connection (BQ25895, §6.4). SNVA803 also routes SW/BST on a single layer.
- **Cooling vs EMI conflict:** a hot device wants a big drain pad, which is an antenna ([USPTO 10763221](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10763221)). Resolve it with thermal vias from PGND/EP, not by enlarging SW (Rohm; [HS Electronik](https://hs-electronik.com/news/buck-converter-pcb-layout-hot-loops-feedback-guide)). "Bigger SW copper for cooling" is wrong.
- **Edge-rate tuning:** slowing edges (for example a series bootstrap resistor) cuts dV/dt and EMI at an efficiency cost ([Richtek AN045](https://www.richtek.com/Design%20Support/Technical%20Document/AN045)). LearnEMC: transition times longer than about 1% of the period noticeably reduce efficiency.
- **Inductor dot on SW:** "up to 8 dB" lower E-field emissions when the dotted (inner-winding) end connects to SW. The outer winding at quiet VOUT shields it. H-field is unaffected. VR +CTX: this was measured on **one shielded part (WE-LHMI 74437368022)** ([Würth ANP047 republication](https://www.powersystemsdesign.com/articles/the-behavior-of-electromagnetic-radiation-of-power-inductors-in-power-management/22/11575)). Shielding suppresses only magnetic fields, so orientation still matters ([NextPCB](https://www.nextpcb.com/blog/shielded-vs-unshielded-inductors-emi-pcb-placement), low). Dissent: a DigiKey forum thread, which is not a measurement.
- **Copper under the inductor:** CONTESTED (§0). The RPA default was a top-layer void under unshielded inductors with inner GND solid. IRP's buck pack encodes a `keepout_ring` on F.Cu (resolution "stricter"). Rohm's "no ground layer directly below" would remove L2 too. Treat this as a context switch.

### 1.6 Feedback, Kelvin sensing, AGND/PGND
- **FB/VOS** is high-impedance. Never route it under L or next to SW on any layer. Sense at the COUT pad, not at the inductor.
  - TPS62130: "connect the VOS pin in the shortest way to VOUT at the output capacitor … separated from the VOUT power line/plane" ([DS p.28](https://www.ti.com/lit/ds/symlink/tps62130.pdf)). VERIFIED.
  - SLVA773: do not run FB parallel to SW.
  - MPS: FB resistors "next to the FB PIN … Do not connect FB to these resistors through vias". R2 goes to AGND, R1 to the output cap at the regulation point.
  - Rohm: "Do not wire directly below the inductor and diode, and not parallel to power supply line."
  - LM5163/TPS560430 [S]: route the sense trace on another layer, shielded by GND, especially when R_FB > 100 kΩ.
- **No numeric SW-to-FB clearance exists in any vendor document** (IRP §8). The ≥1–2 mm figure and the "divider within 2–3 mm" figure are heuristics.
- **AGND/PGND:**
  - TPS62130 calls the common AGND+PGND connection to the EP and system plane "mandatory".
  - SLYT614: join the two grounds at a single point, typically the EP.
  - Boost: the join goes close to the PGND pin.
  - MPS: the AGND–PGND link sits close to the VCC decoupling cap, with ≥2 vias.
  - AN-136: one SGND–PGND connection under the controller; solder the EP with multiple vias.
  - A small AGND pour around the feedback parts, not shared with the PGND return ([SchematicsHub](https://schematicshub.com/articles/buck-layout), low).
- **TI internal tension (VR):** the TPS62130 datasheet ties the FB resistors "directly to … the system ground plane", while SLYT614 says not to via quiet grounds into the plane.
- **"Star ground everything"** is context-dependent. On multilayer boards, a solid plane plus a local hot loop, an AGND island and a single tie is what TI and ADI show. A literal star of traces adds inductance.

### 1.7 Gate drive, bootstrap, snubbers
- **Gate loop:** wide, short traces with the driver next to the FET. The Kelvin source return is the top priority, because common-source inductance (CSI) is "more important to eGaN FETs" ([EPC WP008](https://epc-co.com/epc/Portals/0/epc/documents/papers/eGaN%20FET%20Drivers%20and%20Layout%20Considerations.pdf)).
- **Overshoot-free condition:** L_G ≤ ¼·(R_G + R_Source)²·C_GS (EPC; VR addition).
- **TI:** "place the FETs close to the driver"; keep the driver-ground-to-source path as short as possible ([SLUAAM3](https://www.ti.com/lit/pdf/sluaam3); [SLYP754](https://www.ti.com/lit/ml/slyp754/slyp754.pdf)).
- **AN-136:** run the top-FET gate trace with the SW trace (minimal shared loop) and the bottom gate next to PGND.
- **Bootstrap:** C_boot ≥10×C_g and C_VDD ≥10×C_boot (CORRECTED), as close as possible to the driver supply pins.
  - SLUAAM3 (GaN): two VDD caps, the smaller nearest the IC; boot cap at HB/HS; input RC parts at LI/HI.
- **Snubbers:**
  - SLYT614: the RC snubber has "the shortest possible routing between the SW and PGND pins" (no R/C values given; [E2E](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/927858/tps62130a-snubber)).
  - Rohm: the snubber goes at the IC's switching and GND terminals. "Placing it at the both ends of diode will not absorb spike noise."
  - Flyback RCD clamp: HV diode, nF-range C, hundreds-of-kΩ R, optional 100 Ω–1 kΩ in series with the cap ([Infineon AN-1195](https://www.infineon.com/dgdl/an-1195.pdf?fileId=5546d462533600a40153559b13df115a), VR +damping value).
  - Secondary rectifier ringing can be worse than the primary, and Schottkys are especially sensitive; a secondary snubber is sometimes needed ([ADI](https://ez.analog.com/cfs-file/__key/telligent-evolution-components-attachments/00-330-01-00-00-06-34-74/FlybackSnubberDesign.pdf) [S]).
  - Snubber parts as close as possible to the switch node and transformer, using low-ESL SMD parts ([next.gr](https://www.next.gr/tutorials/switching-power-supplies/flyback-snubber-design-tutorial), low).

### 1.8 Current-sense (Kelvin) connections
- **onsemi** ([DN05117](https://www.onsemi.com/download/design-notes/pdf/dn05117-d.pdf)):
  - Sense traces "equal length, equal dimension and as short as possible".
  - Amplifier and shunt on the same side.
  - Use 4-terminal shunts.
  - Traces "terminate at the center of the inside of the pad". This closes the RPA gap about the tap point.
  - Poor layout causes "10% to 15% or more" error.
- **Bourns** ([N1702](https://www.bourns.com/docs/technical-documents/technical-library/current-sense-pulse-power-high-power-resistors/application-notes/bourns_n1702_current_sense_accurate_measurement_appnote.pdf)): for very-low-ohm 2-terminal parts, R_lead + R_lead ≫ R_shunt. Copper TCR is 3900 ppm/°C against <50 ppm/°C for the element.
- **AN-139:** keep the SENSE± gap minimal and run the pair on the far side of a shield plane.
- **AN-136:** sense signals are <100 mV. Run SENSE± in parallel at minimum spacing, with filter R/C at the IC pins. For DCR sensing, R goes at the inductor and C at the IC. A sense-return via must not touch an internal VOUT+ layer.
- **Thermal note:** copper in the sensed path adds temperature sensitivity ([NextPCB](https://www.nextpcb.com/blog/current-sense-resistor-pcb-layout-kelvin-connection), low).

### 1.9 LDO
- Place CIN at the LDOIN/PGND pins, because trace impedance adds to dropout. Route the output through COUT before changing layers or branching. Use copper-plugged vias ([Renesas AN-PM-179](https://www.renesas.com/en/document/apn/da9080-pcb-layout-recommendations) [P]).
- Dissipation is P = (V_IN − V_OUT)·I. Size copper with the §7 methods, not with the unsourced 2 cm²/W.

### 1.10 Machine-actionable rules (PWR-01…17; RPA §1, with VR status)

| ID | Rule | Status / class |
|---|---|---|
| PWR-01 | CIN_HF first, IC layer, 0 vias, gap ≤2 mm (MPS) | Topology is HARD. The mm figure is a soft objective. |
| PWR-02 | Solid GND on the next layer under the hot loop; dielectric ≤0.127 mm; ≥4 layers | Soft, strong |
| PWR-03 | Minimal SW copper; flag if > k×(SW pads + L pad) | VERIFIED; no number |
| PWR-04 | Inductor dot on SW (needs a pin-1 = dot footprint convention) | +CTX (one part) |
| PWR-05 | No sensitive nets under L or near SW, all layers | VERIFIED qualitative; mm is heuristic |
| PWR-06 | FB/VOS Kelvin from the COUT pad; divider at FB | HARD topology |
| PWR-07 | One AGND–PGND tie at the EP (net-tie count = 1) | HARD where the datasheet says "mandatory" |
| PWR-08 | COUT GND near CIN GND | CONTESTED; **remove as default** |
| PWR-09 | Boost {LS FET, D, COUT_HF} loop tight | VERIFIED |
| PWR-10 | ≥1 via/A, parallel arrays, placed outside the CIN–IC path | Soft, strong |
| PWR-11 | Driver adjacent; gate and return paired; Kelvin pin used | VERIFIED + formula |
| PWR-12 | Boot/VDD caps at the pins | CORRECTED (≥10×) |
| PWR-13 | Snubber loop {R, C, switch pins} tight | VERIFIED |
| PWR-14 | 4-wire Kelvin, equal pair, tap at pad interior | VERIFIED |
| PWR-15 | EP vias 0.3 mm at 1.0–1.2 mm pitch | Geometry VERIFIED; tenting CONTESTED |
| PWR-16 | LDO caps at pins; copper sized for P | Partly CORRECTED |
| PWR-17 | FB/comp parts in the IC half-plane away from SW/L (angular-sector test) | Inference |

### Implications for our system
- **Converter role detector + topology table.** Hot-loop membership is derived, not guessed. The LLM only confirms the topology from the datasheet.
- **Score loops with an inductance estimator**, not mm thresholds. Inputs: polygon area, L1→L2 dielectric, via count. Calibrate on AN-139, SNVA803 and EPC anchors, then report nH, the predicted overshoot (L·di/dt; warn if >0.2×V_DS,max per IRP) and the EPC-style efficiency impact.
- **Hard-gate the topology facts:** same layer, 0 vias in the hot loop, FB from the COUT pad, AGND tie count. Soft-score distances.
- **Context switches** for copper under L, CIN/COUT ground separation, PMIC ground cuts (DA9080), the WCSP SW-under-CIN exception, and ≥100 W isolated returns.
- **Emit the SLYT614 order** as `placement_priority`, and treat datasheet ordered lists as overriding it.

---

## 2. Decoupling and PDN

### 2.1 Myths vs reality
- **What matters is mounting loop inductance** (pads, vias, depth to the plane pair), not the capacitor value. Archambeault's title slide: "It's really the inductance that matters!" ([slides](https://ewh.ieee.org/r3/enc/emcs/archive/2012-10-10b_DecouplingMyths.pdf) [P]).
- **"Smallest value closest"** is a proxy that works only because small values come in small packages. In the same package, 0.1 µF and 47 µF MLCCs have the same ESL ([Bogatin](https://passive-components.eu/a-low-cost-capacitor-characterization-system/); MLCC ESL "independent of its capacitance value", [SIJ 2020](https://www.signalintegrityjournal.com/articles/1589-the-myth-of-three-capacitor-values)).
  - The real rule is "lowest mounting inductance closest". VR marks this CONTESTED, because ADI MT-101 (2009) still teaches the conventional scheme: a 10–100 µF electrolytic "no more than 2 in. away" and 0.01–0.1 µF as close as possible ([MT-101](https://www.analog.com/media/en/training-seminars/tutorials/MT-101.pdf)).
- **"Three values per pin" (100n/10n/1n)** is a myth. Three values with equal ESL create "two parallel resonance peaks" (anti-resonances).
  - The series-RLC model holds when mounting L exceeds about 1 nH.
  - A 47 µF electrolytic can have about 30 nH of ESL; a 0.1 µF disc about 7 nH.
- **Archambeault's five tested beliefs:** you need a variety of values; many caps of one value are better; place caps as close as possible; location does not matter; spread caps over the board. His findings:
  - Use the largest value the package allows.
  - The IC draws charge from between the planes; the caps replenish it.
  - Caps deliver charge better when spread out.
  - If caps are close together, alternate their power/ground orientation. The worst case is caps close together with all pins the same way.
  - Deep plane pairs have higher effective inductance.
  - Avoid long thin power/ground structures.
  - With a thick (35 mil) dielectric, "Location does matter!"
- **Location matters on a sliding scale** ([Altium](https://resources.altium.com/p/when-does-decoupling-capacitor-location-matter-pcb)): mounting inductance is location-independent; spreading inductance depends on location. Location matters less on boards with tight planes and matters on 2-layer boards without planes.
- **Ferrite beads on every rail** are often harmful (resonance, saturation, DC drop).
- **Williams (AN47):** "the right (wrong) combination of supply line parasitics and paralleled dissimilar capacitors can produce a resonant, ringing response". Bypassing is "by far the most common error" in high-speed amplifier work. The system should **damp with ESR rather than add decade values**.

### 2.2 Mounting inductance data
- **Axotron** [S, VR VERIFIED] (8-layer board, P–G 75 µm, top-to-plane about 300 µm, bottom about 1200 µm) ([Axotron](https://axotron.se/blog/inductance-of-some-decoupling-layouts/)):

  | Layout | Top side | Bottom side |
  |---|---|---|
  | 0402 with 0.8 mm tracks to vias | 0.63 nH | 1.35 nH |
  | 0402 via-in-pad | 0.44 nH | 1.04 nH |
  | 0306 via-in-pad | 0.29 nH | 0.70 nH |

  Overplated via-in-pad gives a further 15–30%. Via-in-pad costs solder thieving or a fill-and-plate charge ([USPTO 7312402](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7312402)).
- **Archambeault depth table** (VR addition), 0402:
  - 10 mil pad-to-via: **0.9 nH** at 10 mil depth to the planes, **3.2 nH** at 100 mil depth.
  - 50 mil pad-to-via: 1.4 → 4.6 nH over the same depths.
  - Plane spreading on a 10" wide plane: cap-to-IC 10" → 545 pH, 1" → 154 pH. Narrow planes raise inductance sharply.
- **LearnEMC:** on boards with planes, connect power and ground pins with a via adjacent to the pad, not with traces.
- **Hubing anti-rule:** "decoupling caps on both sides of a plane gap" is wrong; the fix is "Don't gap the ground plane!"

### 2.3 Target impedance and its limits
- Z_t = ΔV_allowed / I_transient. Example: 1 V × 5% / 10 A = 5 mΩ. Bands: the VRM covers up to roughly 100 kHz, board caps the middle band, and package/die capacitance roughly ≥50 MHz. Board mounting inductance sets a floor below which more caps do not help ([ICD](https://www.icd.com.au/articles/TargetZ_Design007-Feb2018.pdf); [MPS](https://media.monolithicpower.com/mps_cms_document/a/i/aip_meeting-the-impedance-mask_strategies-for-pdn-design-and-optimization_r1.0.pdf); [Altium PDN guide](https://files.resources.altium.com/sites/default/files/2022-02/PDN%20Simulation%20and%20Analysis%20Guide.pdf)).
- **"Target Impedance Is Not Enough"** (Smith, Sandler and Bogatin, [SIJ 2019](https://www.signalintegrityjournal.com/articles/1083-target-impedance-is-not-enough) [P]):
  - Allocate only the dynamic-transient share of the budget to Z_t. VRM ripple, DC regulation, IR drop and crosstalk take the rest.
  - A **flat** profile below Z_t is "the basic criterion for a robust PDN".
  - Each peak is a parallel RLC with f, peak Z, Z₀ and Q. If rise time is <3.5 ns and the resonance is below 100 MHz, the step response is a damped sine governed by Z₀, so Z₀ ≤ Z_t is required.
  - A square wave at resonance drives the noise to 0.64·Q× the step-response noise after about Q cycles. Hence **peak ≤1.57×Z_t** for a robust PDN, though "many successfully deployed products" reach 3×.
  - Several high-Q peaks excited in sequence can build a **"rogue wave"**.
- **Other methods and tools:**
  - Keysight [S] advocates flat impedance; Witcher & Sandler (DesignCon 2023) [S] add flatness metrics: Q, group delay and NISM.
  - Sandler [S]: bulk capacitance C = L/R².
  - Novak et al. [S] compared synthesis methods (multi-pole, caps-by-the-decade). A related patent uses ESR-controlled banks with ESR ≤ Z_t and N = ESR/Z_t(f) ([DC06](http://electrical-integrity.com/Paper_download_files/DC06_TF-MP3_SUN.pdf); [USPTO 6571184](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/6571184)).
- **Plane cavity modes:** f_mn = (c₀/2√εr)·√((m/a)²+(n/b)²). For a 100 mm FR-4 plane (εr 4.3), f₁₀ ≈ 720 MHz, or f₁₀ ≈ 150/(a[mm]·√εr) GHz. Vias through hot spots couple noise; stitching vias and decoupling lower Q ([rftools](https://rftools.io/blog/pdn-impedance-analyzer) [S]).
- **Plane-pair capacitance** ≈ 38 pF/cm² at d = 0.1 mm, εr 4.3 [D]. Ott: plane capacitance is insufficient below about 500 MHz, so prefer tight signal-to-plane coupling.
- **Tools:** Murata SimSurfing and KEMET K-SIM give bias- and frequency-dependent models and export SPICE/S2P, but both are vendor-locked. **No open-source PDN calculator was found.**

### 2.4 Components: MLCC bias, ferrite beads, trace and via current
- **MLCC DC bias** [S]: an X7R 0402/0603 at 50–60% of rated voltage can lose 30–50%, against 10–20% for 1206/1210. A 10 µF 6.3 V 0402 X5R behaves like about 1.5 µF at 5 V. Start by derating to 50% of rated voltage. Delivered C can be 30–70% below nominal ([Octopart](https://octopart.com/pulse/p/breaking-down-mlcc-surprises); [Ultra Librarian](https://www.ultralibrarian.com/2026/03/05/mlcc-capacitor-selection-ulc)). VR did not re-check these against manufacturers.
- **Ferrite beads** ([Analog Dialogue 50-02](https://www.analog.com/media/en/analog-dialogue/volume-50/number-1/articles/ferrite-beads-demystified.pdf) [P], VERIFIED):
  - Operate at about 20% of rated DC current. At 50% of rated current, inductance drops by up to 90%, and the 100 MHz impedance of a TDK MPZ1608S101A falls from 100 Ω to 10 Ω.
  - A bead plus a 10 nF cap resonated near 2.5 MHz, giving **+10 dB** at a 2.4 MHz ripple.
  - Damping options on the ADP5071 example:
    - (A) series 10 Ω in the cap path, which degrades HF bypass;
    - (B) parallel 10 Ω across the bead;
    - (C) C_DAMP 1 µF + R_DAMP 2 Ω.
  - Weir: above 30–40% of rated current, effective inductance can drop by 50% or more ([slides](https://emcfastpass.com/wp-content/uploads/2017/04/PDN_Ferrite_Beads.pdf)).
  - MT-101: 0.1 µF with 1 nH resonates at 16 MHz. Damp with about 10 Ω in the power line or with a bead, which is resistive above 100 kHz.
- **Trace current:**
  - IPC-2221: I = k·ΔT^0.44·A^0.725 (A in mil², k = 0.048 external, 0.024 internal). For 1 A at 10 °C on 1 oz external copper: A = 16.3 mil², so 11.8 mil = 0.30 mm (VR arithmetic VERIFIED; blogs quoting 20 mil are wrong).
  - IPC-2152 is chart-based and usually allows more current; planes within about 0.5–1 mm act as heatsinks ([semiconductor.tools](https://semiconductor.tools/blogs/07-ipc-2221-vs-ipc-2152) [S]).
  - Rohm's conservative design values: >1 mm/A at 1 oz, >0.7 mm/A at 2 oz; 2 A → 0.53 mm for a 20 °C rise.
- **Via ampacity:**
  - Calculators: a 0.3 mm via carries about 1.9 A with 25 µm plating, or 1.6 A with 20 µm; plating matters more than drill. Other sources say 0.8–1.0 A. About 1.1 mΩ per via in a 1.6 mm board [S].
  - TI SLVA959 IPC-2152 table (1 oz, 10 °C): 6 mil 0.2 A; 8 mil 0.55 A; 10 mil 0.81 A; 12 mil 0.84 A; 16 mil 1.1 A.
  - TI SLAA896 epoxy-filled vias (diameter: R / L / I): 4 mil 2.9 mΩ/1.61 nH/1.4 A; 6 mil 2.1/1.48/1.53; 10 mil 1.3/1.32/2.01; 12 mil 1.1/1.26/2.21; 18 mil 0.7/1.14/2.72.
  - Conflict: 2.6× at 12 mil, likely from different temperature-rise and plating assumptions. **Default to the conservative SLVA959 figure.**
- **Return-path stitching** (PDN-08): put GND vias next to signal vias that change reference.
  - TI (primary): "within 200 mil, closer is better". TI Gen5: within 50 mil. EMA: ≥2 vias within 100–200 mil. The 1 mm and 50 mil figures from blogs are secondary.
  - Stitching caps: TI's primary value is ≤1 µF placed at a **split crossing** (VR CORRECTED the 1–10 nF / 50 mil claim).

### 2.5 Automated PDN workflow (RPA §17; each step is code, not LLM judgement)
1. **List rails** from the BOM and datasheets: V, ΔV budget, I_transient (or I_max × activity) and the frequency band. Z_t = (fraction × ΔV)/I_transient.
2. **Build a lumped model:**
   - VRM as R+L;
   - each MLCC with bias-derated C (SimSurfing/K-SIM data or a derating table), ESR and ESL;
   - mounting L from geometry (§2.2);
   - plane C = εA/d plus spreading L.
3. **Check:**
   - |Z| ≤ Z_t across the band;
   - each peak ≤1.57×Z_t (hard, "robust") or ≤3×Z_t (soft, accepted risk);
   - report Q per peak, and warn when two or more peaks have Q > ~2 (rogue-wave risk).
4. **Fix** with same-value caps (lower ESL), ESR-controlled damping, or a controlled-ESR bulk cap (C ≈ L/R²), not more decade values.
5. **Cavity modes:** compute f₁₀/f₀₁ per plane pair. Flag clock harmonics or edge content within ±10% of a mode, then stitch and decouple at the mode maxima (edges and corners for the lowest modes).

**Rules:**
- PDN-01: local HF cap per power pin, vias at the pads, cap ≤ ~2–3 mm [heuristic].
- PDN-02: order caps by mounting L, not value; bulk within ~10–20 mm [heuristic].
- PDN-03: tight plane pair.
- PDN-04: derive cap choice from Z_t.
- PDN-05: derate before counting.
- PDN-06: bead only where needed, at ≤20% I_rated; flag bead+cap f_res = 1/(2π√(LC)) within ±50% of f_sw.
- PDN-07: IPC sizing plus IR drop, R = ρL/(wt), ρ_Cu = 1.72e-8 Ω·m, 1 oz = 35 µm.
- PDN-08: no plane cuts under signals; stitch at layer changes.
- PDN-09: peak ≤1.57/3×Z_t.
- PDN-10: prefer a flat profile (Q ≲ 1–2).
- PDN-11: cavity-mode check.
- PDN-12: plane pairs high in the stack near the IC side, thin dielectric, no long thin power necks.

### Implications for our system
- **Build an open-source lumped-RLC PDN screener.** None exists, and it is a differentiator. Feed it geometry-derived mounting inductance.
- **Implement "smallest closest" as "lowest mounting L closest"**, ranked by package and via geometry. Alternate cap orientation in clusters.
- **Run BOM-level checks** before layout: DC-bias derating, bead current ratio, bead-resonance vs f_sw.
- **Use conservative via ampacity**, and record the conflicting values with their provenance.

---

## 3. RF

### 3.1 Core rules
- **Fixed geometry from the module or RF-IC datasheet:** a 50 Ω CPWG/microstrip over continuous ground, the matching network at the pin, and an antenna keep-out polygon from the module figure.
- **u-blox** [P] ([NORA-B2 SIM](https://content.u-blox.com/sites/default/files/documents/NORA-B2-u-connectXpress_SIM_UBXDOC-465451970-3906.pdf); [MAX-M5Q HIM](https://content.u-blox.com/sites/default/files/MAX-M5Q_HardwareIntegrationManual_(UBX-13002460).pdf)):
  - Trace width ≥200 µm; trace-to-ground clearance ≥2× the trace width; arcs preferred, otherwise 45°.
  - If the same-layer GND gap is ≤5× the track width, use the coplanar-waveguide model.
  - A 50 Ω FR-4 microstrip is about twice as wide as the dielectric is thick.
  - In general routing, keep ≥3W from the ground-plane edge.
  - Void the U.FL signal pad on at least the first inner layer.
  - No RF under the module or receiver: the ground distance is only about 100 µm, with tolerances up to 100%. No ground cuts under the module.
  - "No digital routing … beneath all layers of RF traces" (RF-07, HARD).
  - The ≥10 mm of ground beyond the module applies **only to the NORA-B2x6 embedded-antenna variant**.
  - Additions:
    - ground plane ≥24×30 mm, but over 50×50 mm is not recommended (embedded antenna);
    - metal ≥10 mm from the antenna;
    - "first minimize RF trace length, then bus length";
    - "All traces, including low speed or DC traces, must couple with a reference plane";
    - route power through the bypass and bulk caps before the module pin;
    - a stitched ground ring at the board edge, with power planes kept back from the edge;
    - MAX-M5Q: area under the receiver fully solder-masked, with no open vias.
- **Nordic nRF52832** [P via PS v1.0 mirror] ([PS](https://cdn.sparkfun.com/datasheets/Wireless/Bluetooth/nRF52832_PS_v1.0.pdf)):
  - The radio is not 50 Ω, so a matching network is required; it also filters the 2nd and 3rd harmonics.
  - Shunt cap C3 is grounded through **VSS pin 31**, not directly to the plane, for harmonic filtering (RF-03, HARD topology).
  - Inner-layer keep-out directly below the matching circuit.
  - At least one via per VSS pin.
  - ≥2-layer PCB with a ground plane; with a topside RF ground, VSS connects directly to it.
  - The chip supply is filtered and routed separately from digital supplies.
  - Fast digital stays away from the crystal and the supply lines.
  - The reference layout has no bottom-side components.
  - DevZone [S]: continuous ground under the centre pad and the RF path; no plane under the antenna. Use the Nordic reference design, because matching differs between QFN and WLCSP. The "4×4 via grid" was NOT RETRIEVABLE.
- **Espressif ESP32** [P] ([PCB layout](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html)):
  - Antenna on or outside the board edge, feed near the edge; cut the base board on both sides of and below the antenna. Never mid-board with four-side cut-outs.
  - 15 mm clearance is **inside the housing**.
  - 4-layer stack: L1 signals and parts; L2 complete GND with no signals; L3 power plus a few signals, with GND under the RF and crystal; L4 few signals, no parts.
  - Power traces: main ≥25 mil; VDD3P3 ≥20 mil; others 12–15 mil. At least two vias when main power changes layers.
  - Chip ground pad uses ≥9 vias.
  - CLC match in 0201, close to the pin in a zigzag. A 15 mil, 100 Ω ±10% 2nd-harmonic stub on the shunt cap's ground pad (not needed for 0402 and up).
  - RF trace on the outer layer, no vias, constant width, no branches. Keep all layers clear under the IPEX connector. On 2-layer boards the RF trace is normally >20 mil.
  - Keep the antenna away from crystals, DDR, HF clocks, USB and UART.
  - Other numbers:
    - SDIO: ±50 mil to CLK, 50 Ω ±10%, ≤2000 mil;
    - touch traces ≤300 mm long, ≤0.18 mm wide, 0.5–1 mm gap to ground, electrodes 8–15 mm;
    - supply ripple <80 mV (MCS7 at 11n) and <120 mV (11 MHz at 11b).
- **Separation and shielding** (RF Essentials/AtlasPCB, low):
  - ~20 mm from SMPS (NOT FOUND in primary sources); LNA input as far as possible from the SMPS.
  - Shield-can ring: 0.5–1.0 mm ground pad with vias at ≤1.0 mm pitch.
  - Fence ≥3× substrate height from the trace; double staggered rows for TX/RX isolation; 30–70 dB shielding (rough).
- **Via fences:** pitch < λ_g/20 at the maximum frequency ([Wikipedia](https://en.wikipedia.org/wiki/Via_fence)). Single-via self-resonance is a few hundred MHz to a few GHz. At 77 GHz, λ/20 ≈ 0.1 mm, which needs microvias ([AtlasPCB](https://www.atlaspcb.com/blog/gcpw-coplanar-waveguide-pcb-design-rf-mmwave/), low).
  - Worked values [D] (εr 4.3; conservative for microstrip):
    - 2.4 GHz: λ_g ≈ 60 mm → λ/20 ≈ 3.0 mm, λ/10 ≈ 6 mm;
    - 5.8 GHz: λ/20 ≈ 1.25 mm;
    - 1 GHz: λ/20 ≈ 7.2 mm.
  - With the u-blox 2 mm figure gone, λ/20 at the highest harmonic of concern is the working default, but as a **soft** objective.
- **Bends:** the 90° myth traces to one 1971 MECL figure. Bogatin's data shows a 5-mil corner (8.5 fF) has no effect until well over 70 GHz. Johnson: corners are fine to 2 Gbps and just beginning to matter at 10 Gbps. A simulation found 20 dB from mitering at 77 GHz; mitering may be worth it from about 5.8 GHz ([Altium](https://resources.altium.com/p/slaying-900-right-angle-bend-dragon); [GaTech](https://tentzeris.ece.gatech.edu/ECTC09_Rida.pdf)). Acute angles are a fab acid-trap concern. On RF use arcs or 135° (Espressif, u-blox).

### 3.2 Rules RF-01…09 (RPA §3, with VR status)

| ID | Rule | Status / class |
|---|---|---|
| RF-01 | Z0 geometry from a field solver; continuous reference | VERIFIED + additions |
| RF-02 | Point-to-point RF net; no stubs, test pads or T-branches except designed matching | Physics; stub ≪ λ/10 heuristic |
| RF-03 | Match within ~1 mm of the pin [heuristic]; shunt grounded at the named pin | HARD topology |
| RF-04 | Fence pitch ≤ λ_g/20 | Numbers NOT FOUND in primary; soft |
| RF-05 | Keep-out on all layers | **Split:** HARD PCB polygon from the module figure + enclosure clearance exported to the mechanical checklist |
| RF-06 | Separation from SMPS/clocks | Soft (no primary number) |
| RF-07 | Only GND under RF | HARD |
| RF-08 | Arcs/135° above a few GHz; acute angles banned everywhere | Context-scoped |
| RF-09 | Pour stitching ≤ λ/20 (λ/10 looser) | Soft; also see the perimeter-stitching conflict (Hubing: perimeter-only stitching can form a resonant cavity; Ott: stitch the periphery) |

### Implications for our system
- **Per-part RF data is primary.** Store keep-out polygons, stacks, stub specs and power-trace widths per module or chip, never generalised. Pull keep-outs from datasheet figures (vision extraction), with human review.
- **Encode antenna keep-outs** as KiCad rule areas (disallow tracks, vias and zones on all layers). Put enclosure clearance in a separate mechanical report.
- **The RF net-class `RF50`** gets width and gap from the stackup solver, point-to-point topology, arc corners, fence and stitching scoring, and a reference-integrity raster.
- **Treat RF-to-SMPS distance as a ranked objective**, and prefer fencing or cans when the board is dense.

---

## 4. Analog, mixed-signal, precision sensing and crystals

### 4.1 Ground strategy
- **One solid plane, partitioned placement, ADCs straddling the boundary.** Splits force return currents into large loops ([Ott](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html) [P]; [TI SLYT512](https://www.ti.com/lit/an/slyt512/slyt512.pdf)). If a split is unavoidable, use one bridge and route every crossing over it.
- **Ott details [P]:**
  - LSB at a 1 V reference: 8 bit 4 mV; 10 bit 1 mV; 12 bit 240 µV; 14 bit 60 µV; 16 bit 15 µV; 20 bit 1 µV; 24 bit 60 nV. Keep ground noise below the smallest signal of concern.
  - A single partitioned plane is "usually adequate" for 8–12 bits.
  - For ≥14 bits, use isolated analog/digital regions, each solidly connected to the digital plane under each ADC, with **no trace on any layer crossing the slots**.
  - Test procedure: split with jumpers every ½ inch and compare open vs closed. "In almost all cases … better with the single ground plane."
  - On datasheet "AGND+DGND to the analog plane" advice he asks: where does the digital decoupling cap's ground go? His answer is one plane from the start.
- **ADI MT-031** [P] ([MT-031](https://www.analog.com/media/en/training-seminars/tutorials/MT-031.pdf)):
  - Treat low-digital-current converters as analog parts. Join AGND and DGND externally to the analog plane with minimum lead length. Connecting DGND to a digital plane "invites disaster". Bryant adds: "even if the data sheet suggests otherwise".
  - Decouple VD with 0.01–0.1 µF to DGND, plus an optional small lossy bead.
  - Put a buffer register next to the converter outputs, with series R (example: 500 Ω × 10 pF → t_r ≈ 11 ns).
  - About 0.2 pF of stray capacitance exists between every pin of an IC package.
  - More than 300 mV between separate ground planes can damage ICs or cause latch-up. Put back-to-back Schottkys at the star if planes are separate.
- **TI SLYT499:** join AGND and DGND to the same low-impedance plane with minimum length.
- **ADI EngineerZone:** some multi-device datasheets (AD5522) specify their own scheme, and that wins.
- **Hubing 2019:** "more than one 'ground'" is MOST EGREGIOUS. Provide one solid plane under all digital logic. LearnEMC also calls ground islands under ICs "a bad idea".
- **Low-frequency exception** (Altium/Peterson): below about 100 kHz, return currents do not hug the trace. Audio and precision DC may need engineered return paths and a star at the power entry (see §6.6).
- **Pease:** for high isolation, build the analog section separately, possibly in a shielded box, and expect copper fences. 35 dB of rejection is feasible; 50 dB takes "all those extreme efforts" ([Pease Lab Notes](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/1023/Bob-Pease-Lab-Notes-Part-7.pdf) [P]).

### 4.2 Op-amps, guards, thermal EMF
- **Guard rings** ([TI AN-241](https://www.ti.com/lit/an/snoa664/snoa664.pdf) [P]):
  - Drive the guard from a low impedance at the input's potential: +IN potential for inverting configurations, −IN for non-inverting.
  - Guard both sides. Surface leakage is "virtually eliminated"; double-sided guarding cuts bulk leakage by "about an order of magnitude".
  - The mask-free guard claim was not verified.
- **Summing node:** the inverting node is the most parasitic-sensitive ([Op Amps for Everyone](https://web.mit.edu/6.101/www/reference/op_amps_everyone.pdf)). Williams: 1 pF across a 1 kΩ feedback resistor caused severe peaking. "Minimize trace area and stray capacitance at critical nodes. Consider layout as an integral part of the circuit" ([AN47](https://www.mit.edu/~6.331/an47fa.pdf) [P]).
- **Thermal EMF:** about 200 nV/°C at dissimilar-metal junctions. Use symmetric, isothermal layouts ([Electronics360](https://electronics360.globalspec.com/article/9981/pcb-layout-for-precision-operational-amplifiers), low).
- **Pease:** "more than 50 rules" exist for matching; common-centroid is "usually very easy, using the rules of symmetry".
- **Rules:**
  - AMS-01: one plane, region partition.
  - AMS-02: AGND+DGND to the analog plane at the package.
  - AMS-03: if split, exactly one bridge, crossings over it.
  - AMS-04: converter decoupling to AGND; digital interface buffered near the converter.
  - AMS-05: guard high-Z inputs.
  - AMS-06: feedback resistors at IN−; summing node ≤ ~3 mm [heuristic].
  - AMS-07: precision parts symmetric and away from heat.
  - AMS-08: crystal rules.
  - AMS-09: Kelvin for all precision sense points.

### 4.3 Sensor front ends (RPA §15; the dominant error decides the rules)
- **Thermocouple** ([TI SBAA274](https://www.ti.com/lit/pdf/sbaa274) [P]):
  - Every dissimilar-metal joint is a junction, so connections must be "simple and symmetric".
  - The cold-junction (isothermal) block is often a connector with large metal mass, or copper fill layered top and bottom. The CJ sensor (diode, thermistor or RTD) error passes straight into the result. An enclosure may be needed against air currents.
  - Seebeck coefficients (µV/°C at 0 °C): J 50.37; K 39.48; T 38.74; E 58.70.
  - Rules: SEN-01 (CJ sensor on the connector's copper island; TC± symmetric, same layer, same vias) and SEN-02 (heat sources away; ≥15–20 mm from >0.5 W parts [heuristic]).
- **Bridge** ([SBAA532A](https://www.ti.com/lit/an/sbaa532a/sbaa532a.pdf) [P]; [TIDUB00](https://www.ti.com/lit/pdf/tidub00) [P]):
  - 6-wire Kelvin sense, with the excitation also driving V_REF (ratiometric).
  - Parasitic thermocouples and ADC bias current through lead and filter resistance add offset. AC excitation cancels them.
  - Bridge traces "as short and balanced as possible"; the terminal block placed so the input resistors connect closely; R_G at the amplifier pins.
  - Rule: SEN-03.
- **Photodiode TIA, two opposite regimes (SEN-04):**
  - High speed: "ground pour … removed in the areas around the inverting input … on both layers"; C_F is needed for stability; 49.9 Ω back-termination with a 50 Ω microstrip ([TIDU535](https://www.ti.com/lit/pdf/tidu535) [P]).
  - Ultra-low current (fA–pA): guarded, "well shielded" input. Resistors carry about 0.5 pF stray. Use low-leakage, low-dielectric-absorption caps (C0G, polycarbonate, polystyrene, silver mica) ([SBOA034](https://www.ti.com/lit/an/sboa034/sboa034.pdf) [P]). Guard through-hole cathode pins on the bottom too (LMP7721 E2E [S]).
  - Regime thresholds are the note author's [D]: high speed is BW ≳ 100 kHz with R_F ≲ 1 MΩ; ultra-low is R_F ≳ 100 MΩ.
  - SEN-05: R_F∥C_F directly across IN−/OUT, with minimal IN− copper.
- **SEN-06:** pick the partition strategy from ADC resolution in the BOM: one plane for ≤12 bits, isolated regions for ≥14 bits (Ott).

### 4.4 Crystals (RPA §4 + IRP §7 + VR)
- **ST AN2867** ([Rev 19, ECS copy](https://ecsxtal.com/store/pdf/stm32-microcontroller-application-note.pdf) [P], VERIFIED):
  - As close as possible; a grounded guard ring is "essential"; a dedicated oscillator ground plane tied to the nearest MCU ground.
  - **Do not connect a metal can to oscillator ground.**
  - Symmetric load caps. Conformal coating is "highly recommended" for LSE in humid environments.
  - Its listed faults include "too many test points" and "no symmetry".
  - C_s = pin capacitance + PCB parasitic. Gain margin must exceed 5. PC13 activity can shift the LSE frequency.
  - Pull example: 0.175 pF × 45 ppm/pF ≈ 7.8 ppm. Choose LSE C_L ≥6 pF (7 pF is a compromise).
  - No mm values anywhere.
- **Microchip dsPIC33AK** [P]:
  - Oscillator ≤½ in (12 mm) from the pins, same side, load caps next to the crystal.
  - A grounded pour with no signal or power inside; on 2-sided boards, no traces under the crystal on the other side.
  - Tie broken guard sections to a mirrored ground layer.
- **Espressif:**
  - Crystal ≥**2.7 mm** (ESP32) or ≥2.0 mm (ESP32-S3) from the clock pin. This is a lower bound.
  - No vias on clock traces; dense ground vias around them; series parts near the chip; load caps on both sides of the crystal.
  - No traces under the crystal; no magnetics nearby; a top-layer keep-out ring when ground is sufficient.
- **Parasitic budgets:** AVR186 typicals XIN–GND 1 pF, XOUT–GND 2 pF, XIN–XOUT 0.5 pF. AN826 stray 2–5 pF. TUSB9261 C_SHUNT 4.5 pF with a 20 pF load. AN-1469: C_L1 ≈ 2·C_L − 7 pF (start at 33 pF). SWRA495L: about 2–3 pF internal + 7 pF external = 9 pF; 802.15.4 needs ±40 ppm.
- **AVR186:** XIN cap first and closest; C0G caps; XIN and XOUT apart; keep cap grounds clear of USB, RS-232, LIN, PWM and power return currents.
- **SLAA322D:** never route ground between the caps or around the crystal; guard ring to AVSS only; housing to ground.
- **Qualcomm:** a C-shaped ring of GND vias at every clock and RF transition.
- **Conflicts:**
  - Metal can: ST says not to oscillator ground; TI and AVR say housing to ground.
  - TUSB9261: "VSSOSC should not be connected to the PCB ground plane".
  - Copper under the crystal: most say solid ground; CDCE925 [S] says cut the planes.
  - Digest note: ST's dedicated oscillator ground island sits uneasily with Hubing's "ground islands under ICs" anti-rule.
- **IRP rules:** XTAL-DMAX (12 mm), XTAL-DMIN (vendor), XTAL-SIDE, XTAL-CAP, XTAL-PAR, XTAL-SEP, XTAL-GUARD, XTAL-SER, XTAL-MAG, XTAL-CAN (vendor switch), XTAL-TP.
- **Placement is an annulus:** min(vendor) ≤ d ≤ 12 mm. Score trace capacitance = length × C′(stackup) against the pF budget. RPA's "≤5 mm" stays a heuristic.

### Implications for our system
- **Choose the ground strategy by rule:** ADC resolution plus datasheet mandates select single-plane, isolated regions or a bridged split, and each selection activates its own checks (slot crossing, net-tie count, 300 mV check).
- **TIA regime classification must precede any copper rule**, because the two regimes call for opposite actions.
- **Precision symmetry:** add matched-pair mirror metrics and isotherm distance checks to heat sources.
- **Crystal pack:** a distance window, a pF budget, a guard rule area, zero test points, and vendor switches for can and VSSOSC grounding.

---

## 5. Isolation, creepage, clearance and high-voltage safety

### 5.1 Method (TI SLUP419 [P], [PDF](https://www.ti.com/lit/pdf/slup419))
Safety spacing is a lookup chain, not one DRC number:
- **Insulation grade** (functional, basic or reinforced) comes from the end-product standard.
- **Creepage** = f(working V_RMS, pollution degree, material group by CTI). Double it for reinforced insulation.
- **Clearance** = f(rated impulse voltage from mains voltage × overvoltage category, PD, altitude). For reinforced insulation, go one impulse step higher, or use the reinforced column of IEC 62368-1 Table 10.
- **Above 2000 m**, multiply clearance by the IEC 60664-1 Table A.2 factor.
- **Tables by equipment:** IEC 60664-1 F.4 (general); IEC 62368-1 Table 17 (AV/ICT); IEC 61800-5-1 Table 10 (motor drives); IEC 62109-1 Table 14 (solar).
- **IPC-2221B and the stricter IPC-9592B** address "functional operation only and do not address user safety".
- **Coating** can lower the pollution degree (IEC 60664-3), or IEC 62368-1 Table G.13 can be used for coated boards.

### 5.2 Table subsets reproduced by SLUP419
- **Material groups (CTI):** I ≥600; II 400–600; IIIa 175–400; IIIb 100–175. TI isolators are group I. Typical FR-4 is III/IIIa.
- **Pollution degree:**
  - PD1: none, or dry non-conductive (coated boards);
  - PD2: occasional condensation (offices, labs, server enclosures);
  - PD3: conductive (industrial);
  - PD4: continuously conductive (outdoor).
- **OVC:** I (protected circuits) through IV (origin of installation).
- **F.4 creepage (mm):**

  | V_RMS | PD1 | PD2 I | PD2 II | PD2 III |
  |---|---|---|---|---|
  | 63 | 0.2 | 0.63 | 0.9 | 1.25 |
  | 400 | 1.0 | 2.0 | 2.8 | 4.0 |
  | 800 | 2.4 | 4.0 | 5.6 | 8.0 |
  | 1000 | 3.2 | 5.0 | 7.1 | 10.0 |

  RPA's "250 V ≈ 2.5 mm, MG III" figure is from memory and needs checking against the standard.
- **F.1 impulse (V_peak), OVC I/II/III/IV:**
  - ≤50 V: 330/500/800/1500;
  - ≤150 V: 800/1500/2500/4000;
  - ≤300 V: 1500/2500/4000/6000;
  - ≤600 V: 2500/4000/6000/8000.
- **F.2 clearance** (IEC 62368-1 Table 10 values in parentheses):
  - 0.5 kV: 0.04 (PD1) / 0.2 (PD2) / 0.8 mm (PD3);
  - 1.5 kV: 0.5 (0.76) mm at PD1–2, 0.8 mm at PD3;
  - 2.5 kV: 1.5 (1.8) mm;
  - 4.0 kV: 3.0 (3.8) mm;
  - 6.0 kV: 5.5 (7.9) mm.
- **Worked example** (265 V, OVC II, PD2, 5000 m, reinforced): creepage 4 / 5.6 / 8 mm for MG I / II / III; clearance 3.6 × 1.48 = 5.33 mm.
- **When spacing cannot be met:**
  - A slot adds creepage, not clearance. Minimum slot width: 0.25 mm (PD1), **1.0 mm (PD2)**, 1.5 mm (PD3).
  - Coating helps clearance.
  - For functional isolation only, a routine hi-pot at 2×V_working + 1000 V (265 VAC → 1530 V) can substitute.
  - **Common trap:** a group-I package (4 mm) on a group-IIIa PCB (8 mm needed). The usual fix is a slot.
- **TI SLLA284G** ([digital isolator guide](https://www.ti.com/lit/pdf/slla284) [P]):
  - ≥4 layers, stacked HS signal / GND / power / LS signal.
  - **No traces, vias or pads under the isolator on any layer.**
  - A groove >1 mm wide counts if creepage + groove width + 2 × depth ≥ required, without weakening the board.
  - A higher package CTI allows a smaller package.
- **PI AN-72** ([InnoSwitch3](https://www.power.com/sites/default/files/documents/an-72_innoswitch3_family_design_guide_20251107.pdf) [P]):
  - >8 mm primary-to-secondary, especially under the IC and transformer. No traces under the IC, and no spark gaps near it.
  - Spark gaps from the secondary terminals to one AC input after the fuse (6.4/5.5 vs 5.4 mm, see §0), and one across the CM choke.
  - A 0.4 mm mylar pad for a heat spreader across the barrier (reinforced).
- **TI BQ76952** uses copper spark gaps (E-prefix) with no part fitted.
- **IPC-2221B Table 6-1** (functional floor; VR CORRECTED B4 rate):
  - 31–50 V: 0.1 / 0.6 / 0.6 / 0.13 mm (B1/B2/B3/B4);
  - 301–500 V: 0.25 / 2.5 / 12.5 / 0.8 mm;
  - above 500 V per volt: B1 0.0025, B2 0.005, B3 0.025, B4 0.00305 mm/V.
  - B1 is internal, B2 external uncoated (≤3050 m), B4 external with permanent polymer coating. **Solder mask is not a B4 coating.** Altitude derating applies. The JLCPCB blog table is an outlier.
- **ISO rules:**
  - ISO-01: classify every net's voltage and every net pair's insulation grade; a missing classification is an error.
  - ISO-02: surface-path creepage per pair; narrow slots do not count.
  - ISO-03: 3-D clearance × altitude factor.
  - ISO-04: barrier keep-out on all layers under isolators, optos and the transformer span, with the slot centreline under the barrier.
  - ISO-05: slot width ≥ PD minimum.
  - ISO-06: spark gaps as copper features.
  - ISO-07: Y-cap from primary bulk+ (or AC after the fuse) to the secondary rail or return, never through controller ground.
  - ISO-08: fuse is the first series element from the AC connector; spacing upstream of the fuse also meets the table (general practice, not primary-read).

### Implications for our system
- **Build a deterministic safety-spacing engine:** (V_RMS, V_impulse from OVC, PD, MG/CTI, altitude, grade) → (creepage, clearance).
- **Add a 2-D surface-geodesic creepage checker** that respects slots ≥ the PD minimum, plus a 3-D clearance checker. KiCad 9+ reportedly has a creepage DRC; this is unverified.
- **The LLM only proposes net voltage classes and insulation grades**, which a human must confirm because they are safety-critical. Apply the stricter of IPC-2221B and the safety standard.
- **Mains-filter layout, MOV/fuse placement and ES1/ES2/ES3 classes are still gaps.**

---

## 6. Circuit-class specifics

### 6.1 Offline flyback (RPA §10; PI AN-72 [P])
- **Four loops,** each tight, and **"No loop area should be placed inside another loop"**:
  1. primary: bulk cap → primary winding → IC drain/source;
  2. clamp: RCD, or a ~200 V Zener + diode, kept away from the PRIMARY BYPASS pin;
  3. secondary: N_S, C_OUT, SR FET, with copper on the SR FET for heatsinking and a short SR-source-to-IC-GND distance;
  4. bias winding.
- **Grounding:**
  - Single-point ground from the input filter cap to the SOURCE copper.
  - On the primary, bias and SOURCE grounds are separate and join once.
  - On the secondary, star at the R_IS node, with separate traces for GND, C_OUT and feedback.
  - Star-connect at the capacitor pad. No signal shares a path with AC switching currents.
- **Placement:**
  - Bypass and feedback caps directly at their pins; R_LS, R_BP, R_FB and R_IS as close as possible to the pins.
  - **Feedback and VOUT connect before the post-filter inductor**; the post-filter L/C sits at the output terminals.
  - With an input π filter, put the inductor between the **negative** terminals of the input caps.
- **Keep-outs:** quiet traces (Y-cap, FB return) stay away from the drain, from "underneath transformer belly", from the switching side of windings, and from the rectifier. Keep drain copper minimal (RFI).
- **Rules:**
  - FLY-01: loop sets identified from the netlist.
  - FLY-02: polygon non-containment test.
  - FLY-03: belly/drain keep-out.
  - FLY-04: FB tap before L_post.
  - FLY-05: one join per side.
  - FLY-06: >8 mm separation plus the creepage engine.
- Only PI's guidance was read; UCC28740 and VIPer guides were not.

### 6.2 Motor drivers and H-bridges ([TI SLVA959B](https://www.ti.com/lit/pdf/slva959) [P])
- **Grounding:** single-point for power distribution, star for signals; partition rather than physically split. On 2-layer boards, "grid" the ground (mesh). Keep via clusters from breaking the plane. With a predriver, isolate its high-current ground and join at the star.
- **Capacitors:**
  - Bulk electrolytics (>10 µF) at the power entry, with multiple vias.
  - Ceramics (<10 µF) right at each half-bridge.
  - Bypass on the IC's layer with no via between cap and pin (vias go into the cap first), less than 0.5 cm (0.2 in) away, with L/W ≤3:1.
  - About 1 nF at the CSA pins; charge-pump and bootstrap caps at the driver.
- **Gate drive:** traces ≥20 mil at 1 oz; the HS gate trace runs alongside SW.
- **Routing details:** teardrops at thin-to-thick and via-to-pad transitions; series parts side by side, not staggered; sense pairs routed around obstacles.
- **Half-bridge layout:** "stack" or "side-by-side". Make the HS-source-to-LS-drain link short and wide, since ringing is an LC effect. Minimise layer jumps in the high-current loop.
- **Shunts:**
  - Low-side: between LS source and the star ground.
  - High-side: near the star, with the first gain resistor at the shunt.
  - Sense lines as a tight differential pair, with a **net tie** to force Kelvin routing; never parallel to switching nets.
  - Trade-off example: 20 A in 1 mΩ dissipates 400 mW for a 20 mV signal.
- **VDRAIN:** a single Kelvin trace to the HS drain, with a net tie (avoids false OCP trips).
- **Thermal:** continuous pours, 1.5–2 oz, direct-connect unmasked vias (20 mil pad / 8 mil hole). Doubling copper thickness halves lateral thermal resistance.
- **Errors in SLVA959** (see §0): the 5.73 °C/W per-via figure, the λ typo, and "90° bends reflect" (not credible at motor frequencies).
- **Rules:** MOT-01 (commutation loop {C_byp, Q_HS.D, Q_LS.S}, ≤ ~5 mm), MOT-02 (SW length/width), MOT-03, MOT-04, MOT-05, MOT-06, MOT-07.

### 6.3 LED drivers ([TI TPS922050](https://www.ti.com/lit/ds/symlink/tps922050.pdf) [P])
- Topology hot-loop rules apply.
- CSP/CSN parallel, short, away from SW and the ground shield. The example uses R_FLT 100 Ω and an optional 1 nF/50 V X7R C_FLT.
- "Do not allow switching current to flow under the device."
- COMP cap at its pin; large GND; thermal vias.
- Rules: LED-01…04, including LED heat kept away from sense and reference parts. MCPCB was not covered.

### 6.4 Chargers and BMS
- **BQ25895** ([DS §11.1](https://www.ti.com/lit/ds/symlink/bq25895.pdf) [P]): "Layout PCB according to this specific order is essential":
  1. input cap at PMID/GND;
  2. inductor at SW, minimal copper, **no paralleled layers**;
  3. COUT near L and the IC;
  4–5. AGND separate from PGND, joined once under the IC (power pad or 0 Ω), with the ground pour kept off power pins;
  6. decoupling at the pins;
  7. EP soldered, with thermal vias;
  8. vias sized for current.

  PMID ≥8.2 µF without OTG, 40 µF (≤2.4 A) or 60 µF (≤3.1 A) with OTG.
- **BQ76952** ([DS §18](https://www.ti.com/lit/ds/symlink/bq76952.pdf) [P]):
  - "The quality of the Kelvin connections at the sense resistor is critical." TC ≤50 ppm; designed for 1 mΩ; paralleled resistors are OK if Kelvin is preserved.
  - 100 Ω + 0.1 µF differential filter (optional 0.1 µF to ground), placed **at the IC, not at the shunt**, with parallel traces from the shunt.
  - REG18 decoupling at the pin; Zener + series R on I2C.
  - 2-layer reference layout (2.75×3.9 in): cells on the left edge, pack on top, wide current paths, E-prefix spark gaps.
- **Cell filters** [S]: 20 Ω / 0.22 µF typical (1 µF OK), up to 100 Ω maximum. SLUAA81: 20 Ω is the minimum for internal balancing; balance FET about 25 Ω; balancing adds current into VC16, causing IR drop.
- **Rules:**
  - CHG-01: ordered placement.
  - CHG-02: SW on one layer, a good default for all bucks.
  - BMS-01…04: Kelvin plus filter at the IC; cell traces in order without crossing; balance resistors spread for heat; high-current path off the monitor ground; spacing classes from cell index × cell voltage (16S Li-ion ≈ 67 V).

### 6.5 High current and busbars
- **Thin-trace copper weights** (JLCPCB): 1 oz 0.10 mm; 2 oz 0.16/0.15; 2.5 oz 0.20; 3.5 oz 0.25; 4.5 oz 0.30 mm (above 2 oz on 2-layer only).
- **TI SNVA419 copper weight:** ≥1 oz for all designs, 2 oz above 3 W, 4 oz above 6 W.
- **SLAA896 trace table** (width → mΩ/in / A): 30 mil 9.68/3.18; 40 mil 7.08/3.63; 50 mil 5.58/4.32; 80 mil 3.41/5.55.
- **Würth PowerBusbar** [P]:
  - Busbars pressed together with press-fit Powerelements and the PCB in one operation; order Powerelement → PCB → busbar.
  - Can replace heavy copper or inlays; capacity is system-dependent; PCBs follow IPC-A-600 and the Würth press-fit spec.
  - [S]: busbar 1.0–1.5 mm; PCB ≤2.0 mm; press-in force 60–350 N per pin, retention 60–80%; transition resistance 100–200 µΩ, which is usually the limit together with the PCB layout.
- **Laminated opposite-current conductors** cut inductance ([AtlasPCB](https://www.atlaspcb.com/blog/heavy-copper-pcb-design-power-electronics-bus-bar/), low).
- **Rules:**
  - HC-01: narrowest-cross-section check on the track/zone graph.
  - HC-02: ceil(I/I_via) vias at the pad where current enters or leaves, with I_via defaulting to 0.8 A.
  - HC-03: heavy copper vs fine-pitch min-space.
  - HC-04: overlap supply and return.
  - HC-05: busbar keep-outs.
  - HC-06: Kelvin shunts.

### 6.6 Audio and class-D
- **TI SLAA896** ([PDF](https://www.ti.com/lit/pdf/slaa896) [P]):
  - 4–6 layers with epoxy-filled vias.
  - Ground balls shorted together on top and stitched to a solid L2.
  - "Smallest decoupling cap … less than 1 mm" from the pin.
  - **Loop budgets (pin-to-pin + 500 pH cap ESL = total):** DREG–GND 650 → 1150 pH; GREG–PVDD 300 → 800; VBAT–GND 650 → 1150; VBST–BGND 250 → 750; VDD–GND 350 → 850.
  - Output, SW and Vsense never adjacent-layer to other signals without a ground layer between.
  - Boost SW carries 5 A.
  - Vsense taps at the speaker terminals, 6 mil, differential.
  - VBST strapped to PVDD under the device on top.
  - AVDD/VDD/IOVDD star-routed at 20–30 mil from the PMIC; the charge-pump cap starred at the PVDD pin.
- **TPA3110D2** [P]:
  - IC centred on the ground plane, PowerPAD vias 0.33 mm at 1.0 mm pitch.
  - HF caps within 1 mm, bulk next to them.
  - EMC snubbers and filters at the IC; output terminals connect at the filter-cap pads.
  - Inputs on the quiet side with top and bottom floods; AGND to the PowerPAD.
- **Others:** SLYT182 [S] (continuous plane); EE Times [S] (small filter loop, speaker connector near the filter).
- **Below about 100 kHz,** plan return paths and star the power entry (Altium).
- **Rules:** AUD-01 (loop-L budget, reusable for any IC that gives one), AUD-02, AUD-03, AUD-04, AUD-05 (flag shared ground copper between high-current returns and audio input references).
- **Gap:** the "pin 1 problem" and cable shields were not researched.

### Implications for our system
- **Each class becomes a rule pack:** detector pattern → roles → loops → constraints, with datasheet ordered lists emitted as `placement_priority`.
- **Net ties are the KiCad mechanism for Kelvin enforcement.** The generator should insert them.
- **Loop-L budgets (SLAA896)** turn "close" into an estimator target for any part that publishes one.

---

## 7. Thermal method

### 7.1 Metrics and rules of thumb
- **R_θJA belongs to the JEDEC test board.** 70–95% of the heat leaves through the board.
  - Influence ranking: PCB design 100%; chip/pad size 50%; package geometry 35%; altitude 18%; ambient 7%; power 3%.
  - 1s vs 2s2p boards shift R_θJA by up to 50%.
  - Ψ_JT is 0.5–2 °C/W against R_θJC 4–15 °C/W; T_J = T_top + Ψ_JT·P. Ψ_JB back-calculates T_J from a board thermocouple. Do not use Ψ_JT with a heatsink ([TI SPRA953D](https://www.ti.com/lit/pdf/spra953) [P]).
- **TI SNVA419C** ([PDF](https://www.ti.com/lit/pdf/snva419) [P]):
  - Rule 1: ≥15.29 cm² (2.37 in²) of two-sided solid copper per watt for a 40 °C rise in still air. Airflow can halve it. Alternatively, area ≥500 °C·cm²/W ÷ (θ_JA − θ_JC). This assumes the EP connects to planes that reach the edge. Inner planes improve a 2-layer design by up to 30%.
  - Rule 2: about 261 °C/W per 12 mil via with 0.5 oz walls. Place as many as fit at 1 mm pitch, connected to as many layers as possible.
  - Rule 3: ≥1 oz; 2 oz above 3 W; 4 oz above 6 W. Example: θ_JA 28.3 → 21.2 °C/W going from 1 to 2 oz.
  - Rule 4: a cut perpendicular to heat flow raised temperature 5.5 °C, against 1.5 °C for a parallel cut. Run traces radially.
  - Rule 5: a bottom heatsink beats a top one, because plastic θ_JT is 50–200 °C/W.
  - Rule 6: superposition "almost works".
  - Constants: λ_Cu ≈ 4 W/cm·K; FR-4 ≈ 0.0023 W/cm·K; h ≈ 10 W/m²K. A 1 cm² square of 1 oz copper laterally ≈ 71 °C/W; FR-4 vertical for 1 cm² ≈ 13.9 °C/W.
- **TI SLMA002H** (PowerPAD):
  - TQFP land ≤ body − 2.0 mm, solder-mask-defined.
  - 5–9 vias are enough for a small die; 0.33 mm vias with 1 oz barrels give barrel copper ≈1% of the land area.
  - Never leave the pad unsoldered.
- **EP via geometry and assembly** (VR):
  - SLOA122: 0.3 mm vias at 1 mm pitch; do not mask (voiding); no spokes; plugging "not necessary or recommended".
  - SLUA271C: about 1.0 mm pitch, 0.3 mm start; tent with mask 0.1 mm larger.
  - Renesas TB389: 1.0–1.2 mm pitch, 0.3–0.33 mm, about 1 oz barrel; tent from the top.
  - Rohm: 0.3 mm at about 1.2 mm. MPS: 10/20 mil near IN/GND.
  - TPS62130: vias under paste filled, plugged or tented.
- **Paste and voids:** 50–70% coverage (TI), 50–80% (Renesas/Maxim). A 1:1 aperture can float the part. Voids: 25% is the point of diminishing returns, but TI uses a 50% limit.
- **Per-via estimates:** about 150 °C/W for 0.3 mm/25 µm in 1.6 mm board, from blogs; a 9-via array ≈17–33 °C/W; filled vias claimed 6–8× better (calculator).
- **Placement** (vendor, low–medium authority):
  - A tall part upstream creates a wake (a 10 mm electrolytic was cited).
  - Sensitive parts go upstream; tall parts align with airflow.
  - Separate hot parts by 5–10 mm (two 2 W parts 5 mm apart share one copper patch and their rises add); keep them out of corners.
  - Electrolytic life halves per 10 °C (an Arrhenius simplification that ignores voltage and ripple; polymer caps differ; a worked example assumed +35 °C near IGBTs) ([CapXon](https://www.capxongroup.com/files/Lifetime%20Compendium_EN.pdf)).
  - 2 in² of copper lowered temperature 10–15 °C (illustrative, JLCPCB).

### 7.2 Screening estimator (runs on every candidate placement)
1. **Power per part:** LDO (V_IN − V_OUT)·I; switcher P_out·(1/η − 1), split across IC, L and diode; resistors I²R; LEDs (1 − η)·P.
2. **Spreading area:** flood-fill the zone graph from the EP through the vias, clipped where lateral R passes a cutoff.
3. **Network:** R_J-pad (θ_JC or Ψ_JB) + 261 °C/W ÷ N vias (scaled for drill and plating) + L/(λWt) + 1/(h·A, both sides).
4. **Superpose** the sources by influence coefficients.
5. **Check** T_J < T_J,max − margin. Sensitive parts (Al-electrolytics, crystals, references, CJ sensors) stay within their limits, with small ΔT to their neighbours.

**Rules:**
- TH-01: EP via array.
- TH-02: fill or tent strategy.
- TH-03: windowpane paste.
- TH-04: copper sized from P.
- TH-05: spread hot parts.
- TH-06: sensitive parts away from and upstream of hot parts (≥10 mm heuristic).
- TH-07: tall parts parallel to airflow.
- TH-08: no SW copper as a heatsink.
- TH-09: never size from R_θJA alone.
- TH-10: ≥15.3 cm²/W.
- TH-11: EP vias at 1 mm pitch, direct-connect.
- TH-12: copper weight by dissipation.
- TH-13: no cuts perpendicular to heat flow.
- TH-14: bottom heatsink.

### Implications for our system
- **A first-order thermal estimator is cheap enough for the placement loop.** SNVA419 says it does not replace FEA.
- **The LLM extracts the inputs** (rail currents, η, θ values) from datasheets. Code computes the result.
- **Thermal aggressor/victim classes** feed the criticality map and the placer's distance penalties.

---

## 8. DFM/DFA and fab limits

### 8.1 Fab profiles (official pages; IRP §10 and VR)

| Parameter | JLCPCB 2L (rec/abs) | JLCPCB ML | PCBWay std | OSH Park 2L | OSH Park 4L |
|---|---|---|---|---|---|
| Trace/space (1 oz) | 0.10/0.10 | 0.09/0.09 (3 mil in BGA fan-out) | 0.10/0.10 | 0.152 | 0.127 |
| Min drill | 0.2 pref / 0.15 | same | 0.15 (≥0.2 no surcharge) | 0.254 | 0.254 |
| Annular ring | 0.25/0.18 | 0.20/0.15 | 0.15 | 0.127 | 0.102 |
| Copper to routed edge | 0.2 | 0.2 | 0.20–0.25 | 0.381 | 0.381 |
| Copper to V-cut | 0.4 | 0.4 | — | — | — |
| Silk line / text | ≥0.15 / ≥1.0 | same | ≥0.15 / ≥0.8 (1:5) | 0.127 (0.076) | same |

All values in mm.

**JLCPCB extras** [P]:
- Copper weights: 2 oz 0.16/0.15; 2.5 oz 0.20; 3.5 oz 0.25; 4.5 oz 0.30 mm (2L only). Multilayer outer copper is 1–2 oz; inner layers default to 0.5 oz.
- Track tolerance ±20%. PTH annular ring at 2 oz ≥0.254 mm; NPTH ring ≥0.45 mm.
- Vias: ≥0.15 hole / 0.25 mm pad (0.1/0.2 only for ≤1 mm ENIG/OSP boards); pad = hole + 0.1 (0.15 preferred); preferred via hole 0.2 mm.
- Hole-to-hole: via 0.2, pad 0.45.
- Clearances:
  - pad-to-track 0.1 (0.09 at BGA); SMD pad-to-pad 0.15 (see the §0 discrepancy); min SMD pad 0.25×0.25;
  - via-to-track 0.2; PTH-to-track 0.28 (0.35 recommended); NPTH-to-track 0.2;
  - inner via-to-copper 0.2; inner PTH-to-copper 0.3;
  - mask bridge 0.10 (0.13 black/white).
- Plugged vias ≤0.5 mm, ≥0.35 mm from openings. **Vias in BGA pads must be filled and plated over.**
- Edges: routed tolerance ±0.2 (±0.1 precision); V-cut ±0.4 mm at 25°, ≥2 mm between V-cuts (3 mm recommended).
- Panels: mouse-bite spacing 1.6 or 2 mm; tooling edge ≥3 mm. SMT panels: 5 mm rails, 2 mm tooling holes, 1 mm fiducials 3.85 mm from the edges.
- Castellations ≥0.5 mm, 1 mm from the edge.
- Impedance ±10% (±5% on request). Dk: 4.5 (2L), 7628 4.4, 3313 4.1, 2116 4.16. Backdrill on 4–32 layers, ≥0.8 mm thick.
- Assembly: IC pitch 0.35 (standard) / 0.40 mm (economic); BGA 0.3/0.5; 01005; panel ≤250×250 mm.
- Component-to-outline 0.2 mm (routed) / 0.4 mm (V-cut) [S].

**Others:**
- PCBWay: hole tolerance PTH ±0.08 / NPTH ±0.05; half-holes ≥0.4; panel spacing 1.6 mm for routing, 0 for V-score.
- OSH Park 4L: FR408HR, 7.87 mil L1–L2 prepreg; no blind, buried or filled vias on 2L.
- Eurocircuits: inner pad isolation = IAR + 0.075 (≥0.200 mm); connected NPTH ring ≥0.30 mm.
- Third-party blog numbers (for example "5 mil") lose to the official pages.

### 8.2 Assembly and mechanical
- **Courtyards (IPC-7351):** excess per side A 0.50 / **B 0.25** / C 0.10 mm. These are solder-fillet goals, not quality classes.
  - Hausherr: customers use 0.10/0.20/0.40; Siemens, Cadence and Zuken users switch courtyard excess off ([PCB Libraries](https://www.pcblibraries.com/forum/placement-courtyard-excess_topic3372.html), VERIFIED).
  - Others [S]: 1.0 mm around BGAs, about 1.5 mm BGA rework clearance; Cadence 0.25–0.3 mm side-to-side and 0.5–1 mm to edge; TI ≥0.508 mm between lands.
- **Tombstoning** (0201/0402 most susceptible) [S]: symmetric pads; thermal relief on plane-connected pads (spokes 0.10–0.20 mm, gaps 0.20–0.30 mm); mirror any via within 1 mm of one pad; balance the paste; longer soak.
- **Fiducials:**
  - 1 mm minimum, 3 mm maximum.
  - Clear area ≥ the radius, preferably the diameter.
  - Edge distance ≥ 7.62 mm SMEMA + clearance.
  - Local fiducials for ≤0.020" (0.5 mm) pitch (others say <1.0 or ≤0.4).
  - Three global fiducials in an asymmetric L, all the same size ([Solutions Mfg](https://www.solutionsmfg.com/images/pdf/fiducial.pdf), CORRECTED).
- **Test points:**
  - 0.100" pitch, 0.050" minimum; pads about 0.035"; 0.125" from the edge; 0.040" from parts, with handlers needing up to 0.138" ([Test Electronics](https://testelectronics.com/info/whitepapers/dft.php)).
  - Flying probe [S]: pads 0.5 minimum / 0.75 mm recommended; spacing 60/80 mil.
  - All on one side.
- **V-score and depaneling** [S]: components ≥2 mm from the V-cut centreline; MLCCs 3–5 mm (5 mm on 0.8 mm boards), because flex cracks pass electrical test and fail later; soft-termination MLCCs near edges. Stress ranking from lowest: push-back, slit, V-groove, perforation.
- **Panels** [S]: rails 5–10 mm; tooling holes 2–4 mm NPTH, asymmetric, ≥2 mm clear; mouse bites 0.5–1.0 mm, tabs 2–3 mm wide every 50–90 mm; parts 1.5–2.5 mm from tabs.
- **Orientation:** polarized parts in one direction, 0/90° only; clear pin-1 marks; avoid THT ([Cadence DFA](https://resources.pcb.cadence.com/home/2024-dfa-guidelines-for-pcb)). FEDEVEL: extra silkscreen on connectors and slots.
- **Mounting holes:** no standard exists.
  - RP2040 reference: NPTH FD 2.75 mm, mask 3.15 mm, **keep-out 6 mm** (other Pi boards 2.7/5.8/6.2).
  - ISO 273 M3 clearance 3.2/3.4/3.6 mm [S]; M3 socket head ≈5.5 mm; about 7 mm used in practice [S].
  - TI: no high-speed traces near mounting holes.
- **Rules:**
  - DFM-01: DRC = absolute limits, router target = recommended + margin; edge copper preferably 0.3–0.5 mm.
  - DFM-02: courtyard non-overlap.
  - DFM-03: tombstone asymmetry ratio > ~2 flags.
  - DFM-04: ≤2 orientations per polarized class.
  - DFM-05: single-sided SMT if it fits.
  - DFM-06: fiducials.
  - DFM-07: test-point coverage.
  - DFM-08: edge and V-score distances by part class.
  - DFM-09: mounting-hole keep-out.
  - DFM-10: HV spacing.
  - DFM-11: silk.
  - DFM-12: 3-D height zones.

### Implications for our system
- **Fab profiles are separate packs** (precedence 10) that set `min` only, with `recommended` as the router's `opt`. Interface and circuit packs set `opt`/`max` and can never relax a fab minimum.
- **Heavy-copper choice feeds back into the footprint pad-gap checks** (HC-03).
- **Mounting-hole keep-out** Ø = max(screw head or standoff Ø + 2×0.5 mm, vendor example).
- **Everything here is native KiCad DRC** (`track_width`, `clearance`, `hole_size`, `annular_width`, `edge_clearance`, `hole_to_hole`, `text_height`, `text_thickness`, `silk_clearance`, `courtyard_clearance`), except tombstone symmetry, fiducial and test-point coverage, and part-class edge distances, which need Python checks.

---

## 9. General expert placement methodology

### 9.1 Order of operations (RPA §7 synthesis)
Experts place in order of constraint rigidity ([EMA](https://www.ema-eda.com/ema-resources/blog/best-practices-for-pcb-component-placement-emd/); [Sierra](https://www.protoexpress.com/kb/pcb-component-placement-rules/)). Altium's "90% placement, 10% routing" is self-described as debatable.
1. **Mechanical:** outline, holes and keep-outs, edge connectors, user-facing parts, height zones, antenna and module at the edge plus keep-outs. Lock them.
2. **Stack-up and plane plan:** GND under every critical circuit; rail planes or pours; analog/digital/RF/power regions; I/O near its connectors (Ott partitioning).
3. **Anchor ICs**, oriented so pin groups face their peripherals; reserve the fan-out area. Place the SoC/BGA centrally ([PCBWay](https://www.pcbway.com/blog/PCB_Design_Layout/BGA_PCB_Layout_Guidelines_Placement_Fanout_and_Routing_b8eeabdd.html)). Fan-out: dog-bone for pitch ≥0.8 mm, plated-over via-in-pad for ≤0.65 mm; outer rows escape on top, inner rows on inner layers; power and ground pins first ([AtlasPCB](https://www.atlaspcb.com/blog/bga-fanout-routing-strategies-dog-bone-via-in-pad/)).
4. **Critical sub-circuits as rigid templates:** converters, crystal, RF match, ADC front end and reference, shunts. Place each as a unit near its consumer or I/O.
5. **Decoupling** at each power pin, before general routing.
6. **The rest by signal flow:** connector → ESD at the connector → filter → transceiver → IC, with hierarchy sheets as clusters.
7. **DFM pass:** orientation, courtyards, fiducials, test points, silk.
8. **Route order:** hot loops and RF (fixed) → sensitive analog/FB → clocks and HS pairs → general → pours and stitching → DRC plus custom checks.

Placement can be scored before routing (ratsnest length, crossings, region congestion, violation counts), which makes iteration cheap.

### 9.2 Practitioners (RPA §19)
- **Feranec** ([P-sec] student review of the FEDEVEL course):
  - Big parts first, room left between MPU and DDR, high-current parts as far away as possible.
  - Decoupling under the BGA; termination resistors at the driver; EMI/ESD parts at the connector; use 3-D models.
  - Fan-out power pins first, with 0.3 mm vias to bottom-side caps: "One and only one via per each power pad. Don't share a power via".
  - DDR is fanned out first and shortest, inner pads first; on the DDR chip, data fans outward and address inward; one topology per group; fan out every pad.
  - Rules quoted: 20H, via aspect ratio ≤10.
  - Read the vendor guide first (NXP DDR3 order: address, differential, control, data); route "piece by piece" from both ends.
  - A community tips list attributed to him ("smaller cap closer", 10 µF+100 nF, connectors on one edge) is third-party.
- **Phil's Lab:**
  - Rough placement, then section-by-section refinement, with decoupling and crystal placement as their own steps.
  - 2-layer boards: parts on one side, solid ground on the other, few vias cutting the plane.
  - No splits under traces; clustered power vias.
  - Course topics: grounding, stack-up, PDN for QFP/QFN/BGA, DDR3 fly-by, GbE, USB HS/eMMC.
- **Pease:**
  - CAD advocates "did not want to talk about thermals. Or crosstalk. Or good grounds."
  - Fast layouts produce hot transistors next to critical ones and noisy buses over analog.
  - "The art of knowing which circuits are critical isn't always written down … wrapped up in the heads of experts."
- **Williams:**
  - Ground planes exist to minimise inductance; 10 nH at 100 MHz is 6 Ω.
  - Mount fast-current parts as close to the board as possible.
  - Single-point critical comparator grounds into the plane.
  - Keep traces short.
  - Probe ground leads ≤1 in; board-mounted coaxial probe points are better.
- **Hubing:** boards laid out "by people trying to adhere to a long list of EMC guidelines are worse than boards laid out by people with no EMC guidance at all". His most common errors: blindly following guidelines; uncontrolled transition times; not following currents; not identifying critical traces; more than one ground; improper decoupling; bypassing filters.

### Implications for our system
- **Template-first, then global placement:** rigid, locally optimised macros for critical blocks, then a global placer minimising ratsnest + crossings + severity-weighted violations (S1 ≫ S2 ≫ S3).
- **Route and freeze critical nets first.**
- **Criticality is tacit (Pease), so the LLM's highest-value job is producing a reviewable criticality map.** Following rules blindly is itself a failure mode (Hubing), so every rule needs scope and provenance.
- **Feranec's fan-out rules map directly onto a fan-out generator:** one via per pad, never shared; DDR inner pads first.
- **20H** is a context switch (§11), not a default.

---

## 10. How datasheets express layout rules, and turning them into constraints

### 10.1 Five statement types (RPA §8)
1. **Qualitative proximity:** "as close as possible to the LDOIN and PGND pins" (Renesas).
2. **Relative priority:** "inductor close to IC, no need to be as close as input capacitor" (Rohm).
3. **Pin- and point-specific connectivity:** "VOS … to VOUT at the output capacitor" (TPS62130); "shunt capacitor … grounded via the VSS pin closest to ANT" (Nordic).
4. **Explicit numbers:** antenna clearance, via-per-amp, MPS <2 mm, Microchip 12 mm, Espressif 2.7 mm.
5. **Ordered procedures** (SLYT614, BQ25895 "this specific order is essential") **and reference figures and designs.** Nordic says to use its reference design because matching differs between QFN and WLCSP.

### 10.2 Translation table (defaults are heuristics to calibrate)

| Phrase | Constraint | Default |
|---|---|---|
| "C as close as possible to pins" (power stage) | `proximity(part, pins, max_gap)` + `same_layer` + `max_vias=0` + rank 1 + `loop_area` metric | ≤0.5 mm (0402/0603), ≤1.0 mm (0805+); MPS primary ≤2 mm |
| "close to IC" (secondary) | lower-priority proximity | 3–5 mm |
| "Connect X to Y at Z" | `connect_at(net, pad)` + `separate_from(power path)` | sense leaves from the Z pad |
| "short and wide" | `max_length` + `min_width` | ≤5 mm; width from IPC |
| "keep away from SW / inductor" | `keepout(class, aggressor, d, layers=all)` | 1–2 mm; no courtyard overlap |
| "do not route under X" | rule area over the courtyard, disallowing tracks and vias | — |
| "ground via near pad" / "via fence" | `via_near` / `via_fence(pitch, offset)` | 0.5 mm; λ/20 (the u-blox 2 mm figure is now unsourced) |
| "mandatory" / "must" | hard (S1) | "should" / "recommended" → S2–S3 |
| numeric keep-out | DRC rule as written | store units, layer and condition |
| layout figure | `relative_placement_template` | extract with a vision model, normalised to pin 1; use as the seed |
| ordered steps | `placement_priority` | — |

### 10.3 VR refinements
- **Prefer comparative constraints over invented millimetres.** Examples: rank orders ("closer than any other part"), distance ratios ("protected IC much further from the TVS than the TVS is from the connector"; "inductor close but less close than CIN"). They are more faithful to the source and still checkable.
- **Add these fields to every rule:** `source_scope` (device family, data rate, power level, enclosure vs PCB), `statement_strength` (mandatory / must / should / as close as possible / good guideline) and `contested_by`. The LLM can then explain why a rule is hard or soft.
- **IRP rule-pack contract.** A rule needs:
  1. a match pattern (part class, pin function, net role);
  2. typed parameters with units, including formulas in W, H or UI;
  3. provenance and precedence (10 fab < 20 interface default < 30 vendor family < 40 device datasheet), with `by_vendor` alternatives and recorded conflicts;
  4. a check backend: K (KiCad DRU), G (geometric), S (simulation budget) or M (BOM);
  5. placement intents (anchor, adjacent, order_along_path, distance_window, same_side, keepout_ring, orientation, max_loop_area), kept separate from routing.
- **IRP resolution policy:**
  1. The highest precedence wins.
  2. Within one level, use `by_vendor[vendor_profile]`.
  3. Otherwise apply the declared resolution, defaulting to "stricter" with an `info` finding that cites both sources.
  4. [S] never overrides [P] at equal precedence.
  5. [D] defaults to warning until calibrated on evaluation-board layouts.
- **Vendor profiles are mandatory.** Values differ 5–25× between vendors. For an unknown vendor, use the tightest primary value with an info note.
- **Worked buck pack** (IRP §11):
  - Roles: `cin_hf` ≤1 µF on VIN/PGND, preferring the smallest package; `cin_bulk` >1 µF; `ind` on SW; `cout`; `rfb_top`/`rfb_bot`.
  - Parameters: cin ≤2 mm (hard window); bulk ≤20 mm; loop 2/10/20 mm²; di/dt 5 A/ns; L1–L2 ≤0.127 mm; 1 via/A; 1 mm/A; SW width ≤2.54 mm; FB divider ≤3 mm [D].
  - Placement: priority order; same side; F.Cu keep-out ring around the inductor.
  - Routing: SW area = inductor pad + minimum connection, 0 SW vias. FB with 0 vias, on a layer other than SW with a GND shield between, not parallel to SW or VIN.
  - Override: a datasheet reference layout (precedence 40) sets the target loop area measured from the evaluation board.
- **Worked crystal pack:** the annulus; pF budgets; a 3 mm HS keep-out [D] on F.Cu/In1.Cu; a magnetics keep-out; XIN/XOUT separation ≥3W [D]; 0 test points; a DRU disallow rule using `insideArea('XTAL_KEEPOUT')` (verify the syntax).
- **KiCad 10 capabilities:** `fromTo()` pad-path conditions and ps units make many rules native. Loop area, plane-edge offsets, topology order and return-via distance remain geometric checks.

### Implications for our system
- **Datasheet "Layout Guidelines" and "Layout Example" sections are the primary input.** Parse them into typed constraints with strength and scope, and extract figures as relative templates. Datasheet constraints override generic defaults.
- **No published taxonomy of datasheet layout language exists.** Building one, with a test corpus, is novel work.

---

## 11. Hard vs soft vs explicit-selection rules (VR §3)

| Class | Rules in this domain | Encoding |
|---|---|---|
| **Hard: DRC/reject** | Fab absolute limits (DFM-01); courtyard non-overlap (DFM-02); IPC-2221B HV floor (DFM-10, raised by the safety standard); JLC silk ≥1.0/0.15 mm (DFM-11) | Board setup + `.kicad_dru` |
| **Hard: topology** | No split or void crossing; single bridge if split; CIN on the IC layer with 0 hot-loop vias (PWR-01 topology); FB/VOS from the COUT pad (PWR-06); one AGND–PGND tie where "mandatory" (PWR-07); shunt cap grounded through the named VSS pin (RF-03); PCB antenna keep-out polygon from the module datasheet (RF-05); no digital under RF (RF-07); AGND+DGND to the analog plane (AMS-02); plus, outside this domain, connector→TVS→IC order with no stub or via, and 0 test points on SerDes | G-type checker; reject the placement or route |
| **Hard within declared scope** | Vendor numbers tied to a family, interface or data rate | Activate only when scope matches; carry `source_scope` |
| **Soft, strong** | PWR-02 next-layer GND ≤0.13 mm; PWR-10 ≥1 via/A; PWR-12 C_boot ≥10·C_g, C_VDD ≥10·C_boot (schematic check); PDN-06 bead ≤20% rated; PWR-15 EP vias 0.3 mm at 1.0–1.2 mm | High-weight cost terms; warnings quoting the source |
| **Soft, weak (heuristic)** | CIN ≤0.5–1 mm (primary: MPS ≤2 mm); crystal ≤5 mm; FB divider ≤2–3 mm; RF↔SMPS 20 mm; λ/20 and 3–5 mm stitching; 2W/3W/5W spacing (express in h and compute crosstalk); 2 cm²/W; thermal spacing; V-score MLCC 3–5 mm | Rank-based objectives, never DRC errors |
| **Context switch (do not emit by default)** | Copper or ground under inductors (Rohm vs TI); PWR-08 CIN/COUT ground (Rohm vs MPS/TI); thermal-via tenting (SLOA122 vs SLUA271/TB389); "smallest cap closest" (MT-101 vs Bogatin/Archambeault); perimeter stitching (Ott vs Hubing); PMIC ground cuts (DA9080 vs one-ground); 20-H (Montrose "fact, not fiction" for high-density multilayer vs Shim/Hubing slightly higher radiation; LearnEMC lists it as debunked); crystal can/VSSOSC grounding; copper under the crystal | Store both variants with a selector (power level, layer count, fab process, datasheet mandate); ask the user or the datasheet; log the choice |
| **Scoped exceptions to myths** | 90° corners are harmless below multi-GHz, but on ESD paths use ≤45° or curves (arcing for radii below about 2.6 mm at 8 kV, SLVA680A) and on RF use arcs or 135° | Corner rule scoped to net classes `ESD_UNPROTECTED` and `RF50` only |

**Severity recalibrations:**
- Remove PWR-08 as a default.
- Split RF-05 into a hard PCB polygon plus a mechanical enclosure clearance.
- Keep AMS-02 at S1, with the datasheet escape kept only for multi-converter parts with specified schemes.
- Datasheet "mandatory" maps to hard.

**Where vendors disagree, they usually optimise different things.** Rohm targets conducted HF noise and inductor Q; TI and MPS target loop area and shielding. So the selector should be the objective, not a vote.

### Implications for our system
- **Encode the class on every rule.** Surface disagreements to the user instead of silently choosing. Hard rules gate the output; soft rules weight the placer's cost.

---

## 12. Automated checkers and role detectors (RPA §20, IRP §11)

### 12.1 Role detectors (netlist + pin names + datasheet text)
- **Converter candidate:** an IC with {SW, LX, PH, SW1/SW2, LX1…} + {VIN, PVIN, VCC} + {PGND, GND, EP}, or two FETs sharing a node with an inductor. Confirm with datasheet keywords.
- **Topology from inductor connectivity:**
  - L between SW and the regulated output, with an FB divider → buck.
  - L between the input rail and SW, with a rectifier from SW to the output → boost.
  - L from SW to GND with a negative output → inverting buck-boost.
  - Coupled windings with a primary FET → flyback/forward.
  - Two SW nodes with one L → 4-switch buck-boost.
- **Converter roles:**
  - CIN_HF: smallest package between input and PGND (ties: lowest value). CIN_BULK: the rest.
  - COUT; FB_TOP/BOT on the FB net; C_BOOT between BOOT/BST/CB and SW.
  - SNUB: series RC from SW to GND.
  - RSENSE: ≤100 mΩ in a power path, with ends at CS±/SENSE.
  - AGND/PGND by pin name.
- **Hot-loop sets** come from the §1.2 table.
- **Offline flyback:** transformer with the primary on the HV bulk net and the other end on a drain. Classify windings (primary, secondary, bias). Roles: clamp; Y-cap (pins on primary and secondary classes); spark gaps; post-filter L (series L after C_OUT before the connector). Constraints FLY/ISO.
- **H-bridge / 3-phase:** N-FET pairs sharing an SH node that goes to a connector; GHx/SHx/GLx/SLx/SPx/SNx/VDRAIN/VCP pins. Roles: per-phase bypass, shunt, CSA filter caps, bulk. Constraints MOT.
- **Charger:** PMID/VBUS/SW/BAT/REGN/BTST/ILIM/TS pins → ordered priority + CHG-02.
- **BMS:** VC0…VCn, SRP/SRN, BAT, PACK, CHG/DSG. Roles: cell RCs at the IC, Kelvin pack shunt, protection FETs on high-current pours. Voltage classes from cell index × cell voltage.
- **LED:** CSP/CSN → sense pair + filter at the IC; SW keep-out under the IC.
- **Thermocouple:** TC connector or TC± nets + NTC/RTD/sensor IC → CJ co-location and symmetric routing.
- **Bridge:** excitation/sense/signal nets of a 4/6-wire connector → ratiometric REF and matched routing.
- **TIA:** op-amp with R_F ≥ ~100 kΩ and a photodiode on IN− → regime classification.
- **Class-D:** OUT±/SW/BST/PVDD/VBST/Vsense → AUD-01…03.
- **Crystal:** OSC_IN|XTAL1|XIN|XTAL_P and OSC_OUT pins + crystal class + caps to GND + optional series R.
- **RF and ADC:** RF pins plus the matching chain; ADC AGND/DGND pins.

### 12.2 Constraint schema (RPA §20B)
YAML records with:
- `type`: loop_area (ordered members, max_mm2, same_layer, max_vias), proximity (with `require_net_match`, for example inductor dot pad = SW), connect_at (with `forbid_shared_copper_with`), keepout (victim class, aggressors, clearance, layers: all), solid_reference (region = hull of the hot loop + 1 mm, layer In1.Cu, net GND) or via_array (drill, pitch, fill);
- `severity` and `source` on each.

### 12.3 Deterministic checks (pcbnew Python / IPC API)
- **Loop area / inductance:**
  - Shoelace area of ordered pad centroids, plus a routed-path-aware version with a via penalty (area += via count × a thickness term).
  - Inductance L ≈ µ0·h·length/width over a plane, or rank ordering.
  - **Promote this to a first-class loop-inductance estimator.** Inputs: pad gap, trace W/L, via count, length to the plane, plane depth. Calibrate on Axotron, Archambeault, SNVA803, AN-139 and EPC, and judge against SLAA896 pH budgets or the EPC/SNVA803 anchors.
- **Adjacency and proximity:** pad-edge distances, same-side test, via count on the shortest copper path (graph search).
- **Reference-plane integrity:** rasterise adjacent-layer zones under regions or along critical tracks; flag voids, slots, foreign nets and split crossings.
- **Coupling:** layer-aware parallel-run length and minimum distance between victim and aggressor (same layer and ±1 layer).
- **Keep-out compliance:** copper on all layers against antenna, module and under-inductor polygons.
- **Via fence and stitching:** maximum GND-via gap along the RF centreline within an offset; pour-stitching maximum gap.
- **Thermal:** EP via count and pitch; estimated power vs connected copper (§7.2); hot-to-sensitive distances.
- **DFM:** courtyards (built in); tombstone asymmetry (copper within 1 mm of each pad); rotation histograms; fiducials; test-point coverage; part-class edge and V-score distances; HV clearance by net class.
- **PDN:** nearest cap and via distance per power pin; derated C vs Z_t; bead resonance vs f_sw; full §2.5 sweep.
- **Specialised geometry:**
  - angular-sector test for FB parts (PWR-17);
  - polygon containment for nested loops (FLY-02);
  - SW copper on more than one layer (CHG-02);
  - SW area cap; narrowest cross-section on the current graph (HC-01);
  - graph test that quiet ground meets power ground at one pad (FLY-05);
  - shared-copper analysis between high-current paths and monitor or audio references (BMS-03, AUD-05);
  - mirror symmetry for matched pairs (AMS-07);
  - TC± route symmetry (SEN-01);
  - IN− copper area (SEN-04/05);
  - cut orientation relative to radial heat flow (TH-13);
  - airflow upstream cone (TH-07);
  - crystal trace-capacitance budget (XTAL-PAR).
- **Safety-spacing engine:** table lookup → surface-geodesic creepage + 3-D clearance (§5).
- **KiCad encoding:**
  - Net classes per role: `PWR_HOT`, `SW`, `SENSITIVE` (FB/COMP/RT/SS/REF/crystal), `RF50`, `HV`, `ANALOG`, `DIGITAL`; widths and clearances generated from IPC and fab limits.
  - `.kicad_dru` rules using `A.NetClass`, `insideArea()` and layer conditions (for example SENSITIVE↔SW ≥1 mm), plus rule areas from keep-outs.
  - Anything DRC cannot express emits **KiCad-style marker reports** that the LLM reads and repairs from iteratively.
  - Verify all syntax against the installed KiCad.

### 12.4 Criticality map (Pease)
Before any geometry exists, the LLM emits a **reviewable list**, each item with severity and provenance:
- hot loops;
- high-Z and summing nodes;
- matched pairs;
- thermal aggressors and victims;
- noisy buses and their sensitive neighbours;
- isolation barriers.

A human corrects it, and the deterministic checks consume it.

### Implications for our system
- **Division of labour:** the LLM does extraction, classification and templating; code does geometry and physics; humans confirm safety classifications and the criticality map.
- **No published system auto-extracts hot loops from netlists.** Validate the detectors on a corpus of open-source KiCad boards with known regulators, and calibrate thresholds on TI, ADI and Espressif evaluation-board layouts.
- **No open-source KiCad plugin implements all the geometric backends.** That gap is our opportunity.

---

## 13. Idea inventory

Tags: RPA = rules_power_rf_analog_dfm.md, VR = verification_rules.md, IRP = interface_rule_packs.md.

1. Put the hot loop first, smallest, on one layer, over a solid plane (RPA§1).
2. Topology table mapping each converter type to hot-loop members vs continuous-current branches (RPA§1).
3. Treat the INTVCC/driver decoupling loop as a second hot loop, ~20 dB lower (RPA§1, VR).
4. Overshoot calculator V = L·di/dt (e.g., 5 A/ns × 2 nH = 10 V) (VR, IRP§8).
5. Loop-inductance anchors: AN-139 table, SNVA803 2/20 mm², EPC 0.4–2.9 nH (RPA§1, IRP§8).
6. Loop-area tiers ≤2 / ≤10 / >20 mm² [D] (IRP§8).
7. Overshoot check: warn if L_est·di/dt > 0.2×V_DS,max (IRP§11).
8. Efficiency-impact estimate from loop inductance, using EPC data (IRP§8).
9. Prefer vertical loops on multilayer boards (EPC/DTU); thinner boards cancel better (RPA§1, VR).
10. ≥4 layers with a ≤0.127 mm (5 mil) L1–L2 dielectric under power stages (VR, IRP).
11. Isolated return for ≥100 W supplies (Hubing exception) (VR).
12. SLYT614 five-step order as `placement_priority` (RPA§1, §7).
13. CIN placed and routed immediately after the IC; no hot-loop vias (RPA§1, VR).
14. MPS <2 mm as the default CIN window, overridable by datasheet (IRP§8).
15. WCSP exception: route SW under CIN; vias in the SW→L path before moving CIN (VR).
16. System vias outside the CIN–IC path (VR).
17. All converter components on one side (VR).
18. EN/PG parts placed last (VR).
19. Never move CBYPASS or the freewheel diode to the far side through vias (Rohm) (VR).
20. Bulk CIN up to ~20 mm from the HF cap (IRP§8).
21. Multiple vias at the power pins; >20 between input caps (MPS) (IRP§8).
22. Rohm via-inductance formula for scoring (IRP§8).
23. Minimise SW copper; flag area > k×(SW pads + L pad) (RPA§1).
24. SW trace width ≤2.54 mm (LM10504) (IRP§8).
25. SW copper on one layer only (BQ25895), a default for all bucks (RPA§13).
26. Cool through PGND/EP vias, never by enlarging SW copper (RPA§1, §5).
27. Edge-rate slowing (bootstrap R) as an EMI-for-efficiency trade knob (RPA§1).
28. Inductor dot on SW; needs a pin-1 = dot footprint convention (RPA§1, VR).
29. Copper-under-inductor as a context switch (TI vs Rohm vs Hubing) (VR).
30. Sensitive-net keep-out under L and near SW on all layers (RPA§1).
31. FB Kelvin from the COUT pad, separate from the power plane (RPA§1, VR).
32. FB divider next to the FB pin, no vias (MPS) (IRP§8).
33. FB on another layer with GND shield when R_FB > 100 kΩ (IRP§8).
34. Angular-sector test: FB parts away from the SW/L half-plane (RPA§1).
35. AGND island with a single tie (net-tie count = 1) (RPA§1).
36. Flag TI's internal FB-ground tension for user selection (VR).
37. Replace literal star grounding with plane + local loop + single tie (RPA§1).
38. PMIC ground cuts (DA9080) honoured only when the datasheet mandates them (VR).
39. Gate loop: driver adjacent, paired return, Kelvin source used (RPA§1).
40. EPC gate-inductance criterion L_G ≤ ¼(R_G+R_S)²C_GS (VR).
41. Bootstrap schematic check: C_boot ≥10 C_g, C_VDD ≥10 C_boot (VR).
42. Smallest driver bypass cap nearest the IC (VR).
43. Snubber loop-area check, placed at the IC SW/GND pins, not across the diode (RPA§1, VR).
44. RCD clamp values plus optional 100 Ω–1 kΩ damping (VR).
45. Kelvin sense: equal pair, same side, tap at the centre of the inner pad edge (VR).
46. Copper TCR (3900 ppm/°C) awareness for 2-terminal shunts (VR).
47. Sense pair on the far side of a shield plane (AN-139) (VR).
48. DCR sensing: R at the inductor, C at the IC (RPA§1).
49. LDO: output routed through COUT before branching; copper sized from P (RPA§1).
50. Converter role detector from pin names, connectivity and datasheet keywords (RPA§20).
51. Topology classifier from inductor connectivity (RPA§20).
52. Role assignment rules for CIN_HF, BULK, COUT, FB, BOOT, SNUB, RSENSE (RPA§20).
53. YAML constraint schema: loop_area, proximity, connect_at, keepout, solid_reference, via_array (RPA§20).
54. Datasheet layout-section retrieval overriding generic defaults (RPA§20).
55. Decoupling ranked by mounting inductance, not value (RPA§2).
56. Alternate cap orientation in clusters (Archambeault) (RPA§2).
57. Spread caps rather than clustering (Archambeault) (RPA§2).
58. Largest capacitance per package (RPA§2).
59. Via-in-pad / short via traces to lower mounting L, weighed against cost and solder thieving (RPA§2).
60. Archambeault depth-to-plane table in the estimator (VR).
61. Plane pairs high in the stack, thin dielectric; avoid long thin necks (RPA§17).
62. Connect power pins with vias at the pads, not traces, when planes exist (VR).
63. Target impedance per rail, with only the transient share of the budget (RPA§17).
64. Flat-impedance criterion; peak ≤1.57×Z_t (robust) or 3× (risk) (RPA§17).
65. Q per peak; rogue-wave warning for multiple high-Q peaks (RPA§17).
66. ESR-controlled damping and C = L/R² bulk instead of decade values (RPA§17).
67. Open-source lumped-RLC PDN screener (none exists) (RPA§17).
68. Plane cavity-mode calculator vs clock harmonics; stitch at mode maxima (RPA§17).
69. MLCC DC-bias derating before counting capacitance (RPA§2).
70. Ferrite beads only on explicit need, I ≤20% rated (RPA§2).
71. Bead+cap resonance check vs f_sw (±50%), with damping methods A/B/C (RPA§2, VR).
72. IPC-2221/2152 width plus IR-drop check per power net (RPA§2).
73. Rohm 1 mm/A (1 oz), 0.7 mm/A (2 oz) conservative widths (VR, IRP).
74. Conservative via-ampacity default, with the conflict logged (RPA§11, §14).
75. Return-via stitching at reference changes; ≤1 µF stitching caps at split crossings (RPA§2, VR).
76. Pre-layout BOM checks: bias derating, bead current, boot ratios (RPA§2, VR).
77. RF geometry from a solver, net class RF50 (RPA§3).
78. RF point-to-point topology; branch and stub detector (RPA§3).
79. Matching network at the pin; shunt grounded through the named pin (RPA§3, VR).
80. Inner-layer keep-out under the matching network (Nordic) (VR).
81. Via-fence and pour-stitching max-gap checker, λ_g/20 (soft) (RPA§3).
82. Worked λ/20 table by frequency (RPA§3).
83. Antenna keep-out as an all-layer rule area from the module figure (RPA§3, VR).
84. Enclosure clearance exported to a separate mechanical checklist (VR).
85. Ground-plane size window for embedded-antenna modules (u-blox) (VR).
86. Stitched ground ring at the board edge, power planes pulled back (u-blox) (VR).
87. RF-length-first, then bus-length placement priority (u-blox) (VR).
88. All traces, including DC, must have a reference plane (u-blox) (VR).
89. Power routed through bypass and bulk caps before the module pin (VR).
90. Solder-mask the area under GNSS receivers; no open vias (VR).
91. Per-part RF data store (Espressif stack, power widths, harmonic stub, touch rules) (VR).
92. Reference-design deference (Nordic QFN vs WLCSP) (RPA§8).
93. RF↔SMPS distance as a ranked objective; fences and cans when dense (RPA§3).
94. Shield-can footprint ring with via pitch (RPA§3).
95. Corner rules scoped: arcs/135° on RF, ≤45° on ESD paths, ignore elsewhere (RPA§3, VR).
96. Acute-angle (acid-trap) check on all nets (RPA§3).
97. One-plane partitioned mixed-signal layout, ADCs straddling (RPA§4).
98. Ground-strategy selector from ADC resolution (≤12 vs ≥14 bit) (RPA§15).
99. Ott jumper test (0 Ω links every ½") as a validation idea (RPA§4).
100. Split-crossing detector; single bridge; crossings over the bridge (RPA§4).
101. AGND/DGND net-tie at the converter package (RPA§4).
102. 300 mV inter-plane limit and back-to-back Schottkys when planes are separate (VR).
103. Converter output buffer with series R near the ADC (VR).
104. Guard-ring net check, driven at node potential, both sides (RPA§4).
105. Summing-node copper minimisation (IN− net length/area) (RPA§4).
106. Matched-pair mirror-symmetry metric; isotherm placement (RPA§4).
107. Common-centroid via symmetry rules (Pease) (RPA§19).
108. Kelvin connections on all precision sense points (RPA§4).
109. Thermocouple CJ-block co-location and symmetric TC± routing (RPA§15).
110. Bridge ratiometric reference and 6-wire Kelvin; balanced traces; R_G at the pins (RPA§15).
111. TIA regime classifier (high-speed vs ultra-low current) driving opposite copper rules (RPA§15).
112. Low-leakage part-type check (C0G, polystyrene, etc.) for electrometers (RPA§15).
113. Ground-noise budget from the LSB table (RPA§15).
114. Crystal distance annulus: vendor minimum ≤ d ≤ 12 mm (IRP§7).
115. Crystal trace-capacitance budget (1/2/0.5 pF; 2–5 pF total) (IRP§7).
116. Crystal guard pour with a single tie and no foreign nets (rule area) (IRP§7).
117. Zero test points on oscillator nets (IRP§7, VR).
118. XIN cap first and closest; series R at the chip; magnetics keep-out (IRP§7).
119. Vendor switches: metal-can grounding, VSSOSC isolation, copper under the crystal (IRP§7).
120. C-shaped GND via ring at clock and RF transitions (Qualcomm) (IRP§7, §9).
121. Safety-spacing lookup engine (V, OVC, PD, MG, altitude, grade) (RPA§9).
122. Surface-geodesic creepage checker respecting valid slots (RPA§9).
123. 3-D clearance checker across slots and bodies (RPA§9).
124. Net voltage-class and insulation-grade classification by the LLM, human-confirmed (RPA§9).
125. Barrier keep-out on all layers under isolators and transformers (RPA§9).
126. Slot-width validity check per PD (RPA§9).
127. Groove credit formula (creepage + width + 2×depth) (RPA§9).
128. Group-I package on group-III PCB trap detector (RPA§9).
129. Hi-pot substitution only for functional isolation (RPA§9).
130. Spark gaps as copper footprints; Y-cap routing check; fuse-first topology (RPA§9).
131. Apply the stricter of IPC-2221B and the safety standard; corrected B4 rate (VR).
132. Flyback loop identification (primary, clamp, secondary, bias) (RPA§10).
133. Nested-loop polygon containment test (RPA§10).
134. Transformer-belly and drain keep-out (RPA§10).
135. Feedback tap before the post-filter L; post filter at the terminals (RPA§10).
136. One star join per side (graph check) (RPA§10).
137. Input π-filter inductor in the negative leg (RPA§10).
138. Half-bridge commutation-loop check {C_byp, HS.D, LS.S} (RPA§11).
139. Gate trace ≥20 mil, paired with SW (RPA§11).
140. Net ties to force Kelvin routing (shunts, VDRAIN) (RPA§11).
141. 2-layer ground gridding/mesh (RPA§11).
142. Teardrops at width and via transitions (RPA§11).
143. In-path passives side by side (RPA§11).
144. Bulk at the power entry, ceramics at the bridge (RPA§11).
145. Flag erroneous vendor numbers (SLVA959 via R, λ typo) via provenance (RPA§11).
146. LED sense pair with filter at the IC; no switching current under the IC (RPA§12).
147. Keep LED heat away from sense and reference parts (RPA§12).
148. Charger ordered-priority emission (BQ25895) (RPA§13).
149. BMS filter at the IC, not the shunt (RPA§13).
150. Cell traces in order without crossing; balance resistors spread (RPA§13).
151. Monitor ground isolated from high-current shared copper (RPA§13).
152. Spacing classes from cell index × cell voltage (RPA§13).
153. Narrowest-cross-section check on the track/zone graph (RPA§14).
154. Vias placed where current enters or leaves pads, not scattered (RPA§14).
155. Heavy-copper vs fine-pitch min-space check (RPA§14).
156. Supply/return overlap (laminated) to minimise loop area (RPA§14).
157. Busbar/press-fit keep-outs; transitions treated as hot spots (RPA§14).
158. Copper weight chosen by dissipation (1/2/4 oz at 3/6 W) (RPA§14, §18).
159. Class-D loop-inductance budgets per pin (pH) (RPA§16).
160. No adjacent-layer coupling for switching outputs without an intervening GND (RPA§16).
161. Output filter at the IC; speaker connector at the filter-cap pads (RPA§16).
162. Inputs on the quiet side with floods (RPA§16).
163. Low-frequency (<100 kHz) explicit return-path planning; shared-ground-copper flag (RPA§16).
164. Thermal estimator: power per part → spreading → network → superposition (RPA§18).
165. Never use R_θJA alone; use Ψ_JB/Ψ_JT correctly (RPA§18).
166. Copper-per-watt check (15.3 cm²/W) and the board-area formula (RPA§18).
167. EP via array as many as fit at 1 mm pitch, direct-connect (RPA§18).
168. Cut-orientation-vs-heat-flow check (RPA§18).
169. Bottom-side heatsink preference (RPA§18).
170. Thermal-via tenting as a context switch tied to the assembly process (VR).
171. EP paste windowpane 50–70%; void-limit selection (25% vs 50%) (RPA§5, VR).
172. Hot-part spreading; corner avoidance (RPA§5).
173. Sensitive parts upstream and away from hot parts; airflow-cone check (RPA§5).
174. Electrolytic life (Arrhenius) for distance-to-heat scoring (RPA§5).
175. Fab profile packs (precedence 10) that set min only; recommended as router opt (IRP§10).
176. DRC at absolute limits, router at recommended + margin (RPA§6).
177. Multi-fab profile table (JLCPCB, PCBWay, OSH Park, Eurocircuits) (IRP§10).
178. Courtyard Level B 0.25 mm default (RPA§6).
179. Tombstone asymmetry metric (copper within 1 mm of each pad) (RPA§6).
180. Polarized-part rotation histogram (≤2 orientations) (RPA§6).
181. Single-sided SMT preference; light parts only on the bottom (RPA§6).
182. Fiducial count, position and asymmetry check, with corrected edge rules (RPA§6, VR).
183. Test-point coverage and pitch checker with corrected clearances (RPA§6, VR).
184. Part-class edge and V-score distances (MLCC 3–5 mm) (RPA§6).
185. Panel and tab geometry rules (RPA§6, IRP§10).
186. Mounting-hole keep-out derived from the screw head + margin; RP2040 6 mm example (IRP§10).
187. 3-D height zones from the enclosure (RPA§6).
188. Silk legibility check with corrected JLC minimums (VR).
189. Expert placement order: mechanical → stackup → anchors → templates → decoupling → signal flow → DFM → route (RPA§7).
190. Pre-routing placement score (ratsnest, crossings, congestion, violations) (RPA§7).
191. Template-first, then global placement with severity-weighted cost (RPA§20).
192. Region partitioning with designated boundary parts (ADC, isolator, connector) (RPA§20).
193. Route critical nets first, freeze, then general routing, pours and re-check (RPA§20).
194. BGA central placement and fan-out by pitch (dog-bone vs via-in-pad) (RPA§7).
195. Fan-out generator: one via per power pad, never shared; DDR first, inner pads first (RPA§19).
196. Termination at the driver, ESD/EMI at the connector (RPA§19).
197. Rough-then-refine sectioned placement (Phil's Lab) (RPA§19).
198. Datasheet statement-type taxonomy (5 types) (RPA§8).
199. Phrase → constraint translation table (RPA§8).
200. "Mandatory/must" → hard; "should" → S2–S3 (RPA§8).
201. Vision extraction of layout figures as relative-placement seeds (RPA§8).
202. Comparative constraints (rank orders, distance ratios) instead of invented mm (VR).
203. Rule fields: applies_if, source_scope, statement_strength, contested_by (VR).
204. Provenance and authority level on every constraint ([P] > [P-sec] > [S] > heuristic) (RPA§20).
205. Rule-pack schema: match pattern, typed units, precedence, backend, placement intents (IRP§11).
206. Precedence ladder 10/20/30/40 and resolution policy ("stricter" + info finding) (IRP§11).
207. Mandatory vendor profiles; tightest primary value for unknown vendors (IRP§11).
208. Datasheet reference layout overrides the target loop area (precedence 40) (IRP§11).
209. Hard/soft/context-switch/scope classification of every rule (VR).
210. Severity recalibrations (drop PWR-08; split RF-05; AMS-02 escape) (VR).
211. Context-dependence flags to avoid over-applying rules (RPA§20).
212. Treat low-authority numbers as soft objectives (RPA§20).
213. Custom Python checks emitting KiCad-style markers for LLM repair loops (RPA§20).
214. Role-based net classes and .kicad_dru generation (RPA§20).
215. Criticality map as a reviewable artefact before geometry (RPA§19, §20).
216. LLM for extraction and classification; deterministic code for checks (RPA§20).
217. Thermal and PDN screening inside the placement loop (RPA§20).
218. Validation corpus of open-source KiCad boards with known regulators (RPA§20).
219. Calibrate heuristics on vendor evaluation-board layouts (RPA§20, IRP§11).
220. Anti-rule list (LearnEMC not-so-good) to stop the LLM from asserting folklore (VR).
221. Guard against "blind guideline following" (Hubing) by attaching scope and rationale (VR).
222. 20-H, perimeter stitching and guard traces as non-default contested rules (VR).
223. Pease separate-board or shield-box escalation for >35 dB analog isolation (RPA§19).
224. Williams: mount fast-current parts low; coaxial probe points (RPA§19).
225. Copper-weight / heavy-copper stackup decisions surfaced early (RPA§14).
226. Bead/LC and capacitor-combination ringing awareness (Williams, MT-101) (RPA§19, VR).
227. Ott/Hubing primary distances reused by power/RF checks (TI 200 mil return vias; LearnEMC via-at-pad) (VR).
