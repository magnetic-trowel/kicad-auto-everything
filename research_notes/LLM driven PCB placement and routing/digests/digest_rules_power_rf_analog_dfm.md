# Digest: rules for power conversion, PDN/decoupling, RF, analog/precision, isolation, thermal, and DFM/fab, plus checkers and role detectors

**Sources**
- **RPA** = `rules_power_rf_analog_dfm.md`, read in full ("§n" means its section n).
- **VR** = `verification_rules.md`: the power, PDN, RF, analog, thermal, DFM and fab rows, plus its hard/soft classification. **VR wins on conflict, and the corrected values are used throughout.**
- **IRP** = `interface_rule_packs.md` §7 (crystals), §8 (switching regulators), §9 (edges and returns), §10 (fab, mounting, assembly) and §11 (schema and worked packs).

**Evidence tags**
- **[P]**: read in the primary document.
- **[P-sec]**: read in full, but the page is a secondary account.
- **[S]**: search snippet only.
- **[D]**: derived by the note author.
- **(low)**: blog or calculator.

**VR status words:** VERIFIED; +CTX (the number is right but a condition was dropped); CORRECTED; CONTESTED; NOT FOUND; NOT RETRIEVABLE.

**Severity:** S1 functional/safety; S2 EMI/thermal/performance; S3 yield/margin; S4 best practice.

---

## 0. Corrections and conflicts at a glance

| Item | Catalog said | Corrected / status |
|---|---|---|
| Bootstrap | C_boot ≈10×C_g; C_VDD ≈10×C_boot | **C_boot ≥10×C_g** (≤10% droop), **C_VDD ≥10×C_boot**. CORRECTED ([TI SLUA887A](https://www.ti.com/lit/pdf/slua887)) |
| IPC-2221B >500 V | B4 +0.005 mm/V | B1 0.0025, B2 0.005, B3 0.025, **B4 0.00305 mm/V**. CORRECTED ([EMA](https://www.ema-eda.com/ema-resources/blog/pcb-clearance-and-creepage-distance-table/)) |
| JLCPCB silk | ≥0.8–1.0 mm (unverified) | **text ≥1.0 mm, line ≥0.15 mm, pad-to-silk 0.15 mm** ([JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities)) |
| u-blox fence | vias ≤0.5 mm from GND edge, ≤2 mm pitch | **NOT FOUND** in NORA-B2, MAX-M5Q or LEA-6, which say only "as many vias as possible". λ/20 is not primary either. |
| Espressif 15 mm | PCB antenna keep-out | **In-enclosure clearance.** The PCB keep-out is the module figure. +CTX |
| RF↔SMPS 20 mm | heuristic | NOT FOUND; primary sources are qualitative. |
| Miter 50–60% | optimal | NOT FOUND. Johnson/Edwards: rounding removes 21% of corner copper; neutralising needs 70–90% removed ([Johnson](https://www.sigcon.com/Pubs/edn/bigbadbend.htm)) |
| LDO "output caps ≤2 mm"; 2 cm²/W | MPS; blogs | The MPS 2 mm is for the **input** and VCC caps. **2 cm²/W NOT FOUND.** |
| PWR-08 CIN/COUT grounds close | inference | CONTESTED: Rohm **≥1–2 cm apart**; MPS/TI close or common. **Drop as a default.** |
| Copper under inductor | TI vs blog | CONTESTED between **two primaries**. TI: top keep-out, L2 GND kept. Rohm: no ground directly below (eddy currents cut L, add loss). Hubing: planes under some chokes are "not a good idea". |
| Thermal-via tenting | tent ≥ via+0.1 mm | CONTESTED. SLOA122: "Do not cover the vias with solder mask". SLUA271/TB389: tent from the top, 0.1 mm larger. |
| EP voids | ≤25% | +CTX: 25% = diminishing returns, but **TI prefers a 50% limit**. |
| Fiducial edge | ≥5 mm | CORRECTED: SMEMA 7.62 mm + clearance (boards); JLC panels: 1 mm fiducials 3.85 mm from the edge on 5 mm rails. |
| Test-point clearance | ≥2.5 mm | CORRECTED: **0.040" (1.0 mm)** to parts; handlers up to 0.138"; 0.125" from the edge. |
| AMS-02 escape | "unless datasheet says otherwise" | ADI (Bryant): tie to analog ground "**even if the data sheet suggests otherwise**". Keep the escape only for multi-converter parts with a specified scheme (AD5522). |
| Guard mask opening | mask-free guard | Not in AN-241; the supporting pages were NOT RETRIEVABLE. |
| SLVA959 via R | 5.73 °C/W per via | **Error in TI's document** (radii and solid annulus). Use ~150–261 °C/W. |
| SLVA959 λ | 25 °C·cm/W | Typo for 0.25; the 71.4 °C/W result matches 0.25. |
| 12-mil via current | 2.21 A (SLAA896) vs 0.84 A (SLVA959) | 2.6× conflict; default to the conservative SLVA959/IPC-2152 value. |
| PI AN-72 spark gap | — | 6.4 mm (5.5 acceptable) vs "at least 5.4 mm" in the same document. |
| u-blox casing | — | ≥10 mm vs 5 mm in the same document. |
| JLCPCB SMD pad spacing | ≥0.10 mm at 1 oz (RPA §6 [P]) | VR/IRP: different-net pad-to-pad **0.15 mm**. Possibly different parameters; **re-check before encoding.** |

**Meta-finding (VR):** snippet-derived numbers were mostly right. Almost every discrepancy was a **dropped applicability condition** (device family, enclosure vs PCB, a single measured part, E-field only). Rules therefore need `applies_if` and `source_scope`.

---

## 1. Switching converters

### 1.1 Principle
- **Hot loop first.** The loop carrying fully switched, high-di/dt current is the dominant EMI source. Make it smallest, place it first, keep it on one layer and put a solid plane directly under it. The on- and off-cycle loops are not the target; CIN sources all the AC currents, which end at COUT ([AN-139](https://theengineer.markallengroup.com/production/content/uploads/2015/01/an139f.pdf) [P]).
- **Ranking after the hot loop:** small SW copper → L next to SW → COUT → FB Kelvin at COUT, routed away from SW/L → one quiet AGND tie.
- **Physics:** V = L·di/dt. 5 A/ns × 2 nH = 10 V ([TI SLYT682](https://www.ti.com/lit/pdf/slyt682) [P]); 1 nH × 1 A/ns = 1 V.

### 1.2 Hot-loop membership by topology (RPA inference, consistent with AN-139 and SNVA731)
The hot loop is the set of branches whose current steps 0→I at each edge; continuous-current branches are excluded.

| Topology | Hot loop | Not hot | Notes |
|---|---|---|---|
| Buck | CIN_HF → HS/VIN → SW → LS/diode/PGND → CIN_HF | L, COUT | Integrated parts: CIN_HF + PVIN + PGND; CIN_HF = smallest-package ceramic |
| Boost | LS (SW→PGND) → rectifier/HS → COUT_HF → PGND | L, CIN | COUT_HF ground by the shortest path to PGND ([SNVA731](https://www.ti.com/lit/an/snva731/snva731.pdf): "most critical PCB feature") |
| Inverting buck-boost | CIN, switch, rectifier and COUT in one series loop | L | CIN and COUT grounds side by side at the IC |
| 4-switch buck-boost | Input half-bridge + CIN; output half-bridge + COUT | L | One HF cap per half-bridge |
| SEPIC/Ćuk | switch → coupling C → rectifier → COUT → GND | L1, L2, CIN | Inference only |
| Flyback | primary, clamp, secondary, bias loops | post LC | Creepage (§5) |
| Half-bridge gate | driver → gate → Kelvin source → return; C_BOOT↔HB/HS | — | Must not share power-source inductance |
| LDO | none | — | Thermal dominates |

### 1.3 Measured loop inductance
- **AN-139 Table 1** (10×10 cm loop at 27 MHz) [P, VERIFIED]: open loop 187 nH; inner shorted loop 141; plate at 1.5 mm 42; non-overlapping rectangle at 1.5 mm 53; plane at 0.5 mm 23; at 0.27 mm 21; **at 0.12 mm (text says 0.13) 13 nH**.
  - A next-layer plane on ≥4 layers is ">3× less" than a 1.5 mm 2-layer board and ">14× less" than single-layer.
  - Mechanism: mirror eddy currents in the plane.
- **Second hot loop:** INTVCC/driver decoupling, about 20 dB below the input loop. Keep it small and shielded by a solid next-layer plane (AN-139; [Kueck Pt 1](https://www.analog.com/media/en/technical-documentation/technical-articles/kueck_layout_power_supply_part_1.pdf)). [Kueck Pt 2](https://www.analog.com/media/en/technical-documentation/technical-articles/Kueck_Layout_power_supply_part_2.pdf): use ≥4 layers, because a 2-layer shield sits >1 mm away.
- **TI SNVA803** (LM5146-Q1) [P] ([SNVA803](https://www.ti.com/lit/pdf/snva803)):
  - Lateral loop ≈20 mm² is still >1 nH, even over an L2 image plane.
  - Vertical loop (L2 return): 2 mm², <500 pH, about 4 V less overshoot.
  - Four 10 nF 0402/0603 caps at the HS drain, grounded through multiple 12 mil vias.
  - SW polygon = inductor pad + minimum FET link; SW/BST on one layer.
- **EPC** [P] ([WP010](https://epc-co.com/epc/Portals/0/epc/documents/papers/Optimizing%20PCB%20Layout%20with%20eGaN%20FETs.pdf); [slides](https://epc-co.com/epc/Portals/0/epc/documents/presentations/High-Performance%20Layout%20Techniques%20to%20Maximize%20GaN%20Device%20Performance.pdf)):
  - 0.4→2.9 nH costs >4% efficiency (1 MHz, 12→1.2 V). Overshoot: 100% of V_in at 1.6 nH vs 30% at 0.4 nH.
  - The "internal vertical" layout ("optimal") uses the first inner layer as the return: about 65% lower L than the best conventional loop; +0.8% / +1% full-load efficiency over vertical / lateral.
  - Vertical-loop L rises up to 80% when the board doubles from 31 to 62 mil.
  - Lateral loops depend on shield distance: 4, 12 and 26 mil tested, 4 mil best.
  - Benchmark loops: Si ≈2 nH, eGaN ≈1 nH.
- **DTU** ([IAS 2020](https://orbit.dtu.dk/files/236953218/IAS_accepted_PCB_for_GaN_2020.pdf)): vertical loops are better but harder to characterise.
- **SLYT682:** a 5-mil core under the loop; no hot-loop vias.
- **Exception (Hubing):** supplies ≥100 W "may require an isolated return" ([LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines)).
- **Area thresholds:**
  - IRP tiers [D], anchored on SNVA803: ≤2 mm² excellent, ≤10 acceptable, >20 fail.
  - Low authority: <10 mm² ([blog](https://embeddedhardwaredesign.com/dc-dc-buck-converter-pcb-layout-design-guidelines/) [S]); boost 1 cm² ([Firgelli](https://www.firgelliauto.com/blogs/engineering-calculators/boost-converter-calculator)).
  - **No primary pass/fail limit exists**, and RPA's YAML `max_mm2: 15` is unsourced.

### 1.4 Placement order and CIN
- **SLYT614** [P, VERIFIED] ([SLYT614](https://www.ti.com/lit/an/slyt614/slyt614.pdf)):
  1. CIN placed first after the IC and routed immediately, "as close … as allowed by manufacturing rules", no vias;
  2. L with minimal SW copper, plus snubber;
  3. COUT and VOS (VOS is "the most critical small-signal connection");
  4. small signal, with EN/PG last ("least important");
  5. single-point ground.

  Also: all parts on one side; system vias "outside the circuit, versus between the input capacitor and IC"; quiet grounds routed back to AGND, not via'd into the plane; 1 via/A, "more is better".
- **WCSP exception** (+CTX): with SW between VIN and PGND, route SW under CIN. Vias in the SW→L path beat moving CIN.
- **Distances:**
  - **Only numeric primary CIN distance:** MPS "<2 mm from the Chip"; VCC cap <2 mm, same layer, no via ([MPS AN065](https://media.monolithicpower.com/document/PCB_Layout_Design_Guidelines_for_NB67xSeries.pdf) [P]).
  - Relative language: SLVA818 "Every millimeter makes a difference!" ([SLVA818](https://www.ti.com/lit/pdf/slva818)); Rohm "even by 1 mm".
- **MPS extras:**
  - VIN/PGND on ≥2 layers with 10/20 mil vias: 1–2 per pin (NB670/1), ≥3 (NB675); >20 between the input caps.
  - VCC cap to AGND ≥4 vias, to PGND 8 (NB675).
  - ≥4 layers, Inner1 = PGND only.
- **Rohm 60AN066E** [P] ([Rohm](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf)):
  - CBYPASS 0.1–0.47 µF on top at the IC; bulk CIN ~2 cm away is fine.
  - Never move CBYPASS ("reverse effect") or the freewheel diode to the far side through vias.
  - L close, but "no need to be as close as input capacitor".
  - Via L ≈ (h/5)(ln(4h/d)+1) nH.
- **AN-136** (Zhang; [mirror](https://docs.ampnuts.ru/analog.com.datasheet/ltc3729l-6/related_data/an136f.pdf) [P]; VR could verify only via snippet):
  - Power stage first; C_HF 0.1–10 µF low-ESL.
  - Power parts on one side, power traces on one layer; layer changes only in continuous-current paths, with multiple vias.
  - "Always have a ground layer next to the outside power stage layer"; ground/DC planes between the power and small-signal layers; never segment planes; thick outer copper.
  - No thermal-relief pads or vias on power parts; cap ± vias close together.
  - Controller near VOUT+ (buck) or VIN+ (boost), away from the hot loop, decoupled at the pins without vias.
  - Multiphase [S]: one 1 µF HF cap per phase kept waveforms stable to 30 A.
- **Boost** ([SLVA773](https://www.ti.com/lit/an/slva773/slva773.pdf) [P]): COUT close; small cap at the IC, bulk farther out; 1 via/A; CIN ground near PGND; large VIN copper is fine (quiet); CIN, COUT and IC grounds "form a Power-Ground".
- **Renesas DA9080 PMIC** [P] ([AN](https://www.renesas.com/en/document/apn/da9080-pcb-layout-recommendations)): input caps on the IC layer; L2 = power-GND return **with GND cuts between bucks** (a vendor-mandated partition that conflicts with the one-ground doctrine); output current on top without vias.

### 1.5 Switch node and inductor
- **SW copper:**
  - Minimise it: SW is "one plate of a parasitic capacitor" (SLYT614); "may work as an antenna" (Rohm); short, wide pour over full GND (TI AAJ); ground under SW shields (AN-136). No source gives an area.
  - SW trace >100 mil (2.54 mm) adds capacitive loading ([LM10504](https://ti.com/document-viewer/LM10504/datasheet/layout) [P]).
  - One layer only: "Do not use multiple layers in parallel" (BQ25895).
  - Cooling vs EMI ([USPTO 10763221](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10763221)): cool through PGND/EP vias; "bigger SW copper for cooling" is wrong.
- **Edge rate:** a series bootstrap R slows edges, trading efficiency for EMI ([Richtek AN045](https://www.richtek.com/Design%20Support/Technical%20Document/AN045)). LearnEMC: edges longer than about 1% of the period noticeably cut efficiency.
- **Inductor dot to SW:** up to 8 dB lower E-field (the outer winding at VOUT shields); H-field unchanged.
  - +CTX: measured on **one shielded WE-LHMI 74437368022** ([ANP047 republication](https://www.powersystemsdesign.com/articles/the-behavior-of-electromagnetic-radiation-of-power-inductors-in-power-management/22/11575)).
  - Shielding is magnetic only, so orientation still matters ([NextPCB](https://www.nextpcb.com/blog/shielded-vs-unshielded-inductors-emi-pcb-placement), low).
  - DigiKey forum dissent: not a measurement.
- **Copper under L:** CONTESTED, a context switch.
  - RPA default: top void under unshielded L, inner GND solid.
  - IRP buck pack: F.Cu keep-out ring (resolution "stricter").
  - Rohm would void L2 too.

### 1.6 Feedback and grounds
- **FB/VOS:** high-Z; never under L or beside SW on any layer; sense at the COUT pad.
  - TPS62130: "in the shortest way to VOUT at the output capacitor … separated from the VOUT power line/plane" ([DS p.28](https://www.ti.com/lit/ds/symlink/tps62130.pdf)). VERIFIED.
  - SLVA773: FB not parallel to SW.
  - MPS: divider "next to the FB PIN … no vias"; R2 to AGND, R1 to COUT at the regulation point.
  - Rohm: "not directly below the inductor and diode, and not parallel to power supply line".
  - LM5163/TPS560430 [S]: FB on another layer with a GND shield, especially if R_FB > 100 kΩ.
- **No numeric SW→FB clearance exists in any vendor document;** the 1–2 mm and "divider within 2–3 mm" figures are heuristics.
- **AGND/PGND:**
  - TPS62130: AGND+PGND to the EP and plane is "**mandatory**".
  - SLYT614: single point, typically the EP. Boost: join near PGND.
  - MPS: join near the VCC cap, ≥2 vias.
  - AN-136: one SGND–PGND link under the controller; EP with multiple vias.
  - Small AGND pour around FB parts, not shared with PGND returns ([SchematicsHub](https://schematicshub.com/articles/buck-layout), low).
- **TI internal tension:** the TPS62130 datasheet ties the FB resistors straight to the system plane, while SLYT614 says not to via quiet grounds into it.
- **"Star everything"** is context-dependent: plane + local loop + AGND island + one tie beats a literal star of traces.

### 1.7 Gate drive, bootstrap, snubbers
- **Gate loop:** wide, short, driver adjacent; Kelvin source first, since common-source inductance "is more important to eGaN" ([EPC WP008](https://epc-co.com/epc/Portals/0/epc/documents/papers/eGaN%20FET%20Drivers%20and%20Layout%20Considerations.pdf)).
  - No-overshoot condition: **L_G ≤ ¼(R_G+R_S)²C_GS**.
  - TI: FETs close to the driver; driver ground-to-source as short as possible ([SLUAAM3](https://www.ti.com/lit/pdf/sluaam3); [SLYP754](https://www.ti.com/lit/ml/slyp754/slyp754.pdf)).
  - AN-136: top gate runs with SW; bottom gate beside PGND.
- **Bootstrap:** C_boot ≥10 C_g and C_VDD ≥10 C_boot, at the pins. GaN (SLUAAM3): two VDD caps, smaller nearest; boot cap at HB/HS; input RC at LI/HI.
- **Snubbers:**
  - RC snubber on the shortest SW–PGND route (SLYT614 gives no values; [E2E](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/927858/tps62130a-snubber)).
  - Rohm: at the IC SW/GND terminals; "at the both ends of diode will not absorb spike noise".
  - RCD clamp: HV diode, nF C, hundreds of kΩ R, optional 100 Ω–1 kΩ series damping ([Infineon AN-1195](https://www.infineon.com/dgdl/an-1195.pdf?fileId=5546d462533600a40153559b13df115a)).
  - Secondary ringing can exceed the primary; Schottkys are sensitive; a secondary snubber may be needed ([ADI](https://ez.analog.com/cfs-file/__key/telligent-evolution-components-attachments/00-330-01-00-00-06-34-74/FlybackSnubberDesign.pdf) [S]).
  - Low-ESL snubber parts at the switch node and transformer ([next.gr](https://www.next.gr/tutorials/switching-power-supplies/flyback-snubber-design-tutorial), low).

### 1.8 Current sense
- **onsemi** ([DN05117](https://www.onsemi.com/download/design-notes/pdf/dn05117-d.pdf)): "equal length, equal dimension and as short as possible"; same side; 4-terminal shunts; terminate "at the center of the inside of the pad" (this closes the tap-point gap); poor layout causes 10–15%+ error.
- **Bourns** ([N1702](https://www.bourns.com/docs/technical-documents/technical-library/current-sense-pulse-power-high-power-resistors/application-notes/bourns_n1702_current_sense_accurate_measurement_appnote.pdf)): for low-ohm 2-terminal parts R_lead ≫ R_shunt; copper is 3900 ppm/°C vs <50 for the element.
- **AN-139:** minimal SENSE± gap, on the far side of a shield plane.
- **AN-136:**
  - Signals <100 mV; parallel pair at minimum spacing, filter RC at the IC.
  - DCR sensing: R at L, C at the IC.
  - Sense-return via must not touch an inner VOUT+ layer.
- **Thermal:** copper in the sensed path adds temperature sensitivity (low).

### 1.9 LDO
- CIN at LDOIN/PGND, since trace impedance adds to dropout; route the output through COUT before branching or changing layers; copper-plugged vias ([Renesas AN-PM-179](https://www.renesas.com/en/document/apn/da9080-pcb-layout-recommendations) [P]).
- P = (V_IN − V_OUT)·I. Size copper by §7, not by 2 cm²/W.

### 1.10 Rule IDs (RPA §1)
- PWR-01 CIN_HF; PWR-02 next-layer GND; PWR-03 SW area ≤ k×(SW + L pads); PWR-04 dot on SW (needs a pin-1 = dot convention); PWR-05 sensitive keep-out; PWR-06 FB Kelvin; PWR-07 tie count = 1; PWR-08 CIN/COUT grounds (CONTESTED, removed); PWR-09 boost loop; PWR-10 vias; PWR-11 gate pair; PWR-12 boot ratios (CORRECTED); PWR-13 snubber loop; PWR-14 Kelvin; PWR-15 EP vias; PWR-16 LDO; PWR-17 FB parts outside the SW/L half-plane (angular-sector test).
- Hard/soft classes are in §11.

### Implications for our system
- **Netlist role detector + topology table** gives the hot-loop members deterministically. The LLM only confirms the topology from the datasheet.
- **Loop-inductance estimator** (area, L1–L2 dielectric, vias), calibrated on AN-139, SNVA803 and EPC. Report nH, the overshoot (warn if >0.2×V_DS,max) and the efficiency impact, instead of mm thresholds.
- **Hard-gate topology** (same layer, 0 vias, FB from the COUT pad, tie count); soft-score distances.
- **Context switches:** copper under L, CIN/COUT grounds, PMIC cuts, the WCSP exception, ≥100 W returns.
- **Emit SLYT614 order as `placement_priority`;** datasheet ordered lists override it.

---

## 2. Decoupling and PDN

### 2.1 Myths vs reality
- **Mounting loop inductance governs, not value.** Archambeault: "It's really the inductance that matters!" ([slides](https://ewh.ieee.org/r3/enc/emcs/archive/2012-10-10b_DecouplingMyths.pdf) [P]).
  - Same package → same ESL: 0.1 µF and 47 µF match ([Bogatin](https://passive-components.eu/a-low-cost-capacitor-characterization-system/); [SIJ 2020](https://www.signalintegrityjournal.com/articles/1589-the-myth-of-three-capacitor-values)).
  - "Smallest value closest" is a proxy; the real rule is "lowest mounting L closest".
  - VR marks it CONTESTED because ADI MT-101 still teaches 10–100 µF within 2 in plus 0.01–0.1 µF as close as possible ([MT-101](https://www.analog.com/media/en/training-seminars/tutorials/MT-101.pdf)).
- **Three values per pin** create two parallel-resonance peaks.
  - The series-RLC model holds when mounting L > ~1 nH.
  - A 47 µF electrolytic can have ~30 nH of ESL; a 0.1 µF disc ~7 nH.
- **Archambeault findings:**
  - Use the maximum C per package.
  - The IC draws charge from the planes; caps replenish it.
  - Spread caps out.
  - In clusters, alternate power/ground orientation; same-direction clusters are the worst case.
  - Deep plane pairs have higher L; avoid long thin power structures.
  - With a 35 mil dielectric, "Location does matter!"
- **Location sensitivity** ([Altium](https://resources.altium.com/p/when-does-decoupling-capacitor-location-matter-pcb)): mounting L is location-independent; spreading L is not. Location matters little on tight-plane boards and a lot on 2-layer boards.
- **Beads on every rail:** often harmful.
- **Williams** ([AN47](https://www.mit.edu/~6.331/an47fa.pdf)): bypassing is "by far the most common error"; dissimilar paralleled caps plus parasitics can ring. **Damp with ESR; don't add decade values.**

### 2.2 Mounting-inductance data
- **Axotron** [S, VR VERIFIED] (8-layer; P–G 75 µm; top-to-plane ~300 µm, bottom ~1200 µm) ([Axotron](https://axotron.se/blog/inductance-of-some-decoupling-layouts/)):

  | Layout | Top | Bottom |
  |---|---|---|
  | 0402 with 0.8 mm tracks | 0.63 nH | 1.35 nH |
  | 0402 via-in-pad | 0.44 nH | 1.04 nH |
  | 0306 via-in-pad | 0.29 nH | 0.70 nH |

  Overplated via-in-pad gives a further 15–30%. Cost: solder thieving and fill/plate charges ([USPTO 7312402](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7312402)).
- **Archambeault** (VR addition), 0402:
  - 10 mil pad-to-via: 0.9 nH at 10 mil plane depth, 3.2 nH at 100 mil.
  - 50 mil pad-to-via: 1.4 → 4.6 nH.
  - Plane spreading on a 10" plane: cap 10" away 545 pH vs 1" 154 pH. Narrow planes raise L sharply.
- **LearnEMC:** connect to planes with a via at the pad, not traces.
- **Hubing anti-rule:** "decoupling on both sides of a plane gap" is wrong; "Don't gap the ground plane!"

### 2.3 Target impedance and its limits
- **Z_t = ΔV/I_transient**, e.g. 1 V × 5% / 10 A = 5 mΩ ([ICD](https://www.icd.com.au/articles/TargetZ_Design007-Feb2018.pdf); [MPS](https://media.monolithicpower.com/mps_cms_document/a/i/aip_meeting-the-impedance-mask_strategies-for-pdn-design-and-optimization_r1.0.pdf); [Altium](https://files.resources.altium.com/sites/default/files/2022-02/PDN%20Simulation%20and%20Analysis%20Guide.pdf)).
  - Bands: VRM to ~100 kHz; board caps the middle; package/die ≥~50 MHz.
  - Mounting L sets a floor beyond which more caps don't help.
- **"Target Impedance Is Not Enough"** ([SIJ 2019](https://www.signalintegrityjournal.com/articles/1083-target-impedance-is-not-enough) [P]):
  - Give Z_t only the transient share of the budget; ripple, DC regulation, IR drop and crosstalk take the rest.
  - A **flat** profile below Z_t is "the basic criterion".
  - Peaks are parallel RLCs (f, Z_peak, Z₀, Q). With t_r <3.5 ns and resonance <100 MHz, noise is governed by Z₀, so require Z₀ ≤ Z_t.
  - A resonant square wave builds to 0.64·Q × the step noise in ~Q cycles → **peak ≤1.57×Z_t** for robust, though many shipped products reach 3×.
  - Sequential high-Q peaks can build a **rogue wave**.
- **Other methods:**
  - Keysight [S]: flat impedance. Witcher & Sandler [S]: add Q, group delay and NISM.
  - Sandler [S]: bulk C = L/R².
  - Novak [S]: synthesis methods compared. Patent: ESR-controlled banks, ESR ≤ Z_t, N = ESR/Z_t(f) ([DC06](http://electrical-integrity.com/Paper_download_files/DC06_TF-MP3_SUN.pdf); [USPTO 6571184](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/6571184)).
- **Cavity modes:** f_mn = (c₀/2√εr)√((m/a)²+(n/b)²). f₁₀ ≈ 150/(a[mm]√εr) GHz ≈ 720 MHz at 100 mm, εr 4.3. Vias through hot spots couple noise; stitching and decoupling lower Q ([rftools](https://rftools.io/blog/pdn-impedance-analyzer) [S]).
- **Plane capacitance:** ≈38 pF/cm² at 0.1 mm, εr 4.3 [D]. Ott: insufficient below ~500 MHz, so couple signals tightly to planes.
- **Tools:** Murata SimSurfing and KEMET K-SIM (bias/frequency models, SPICE/S2P export) are vendor-locked. **No open-source PDN calculator exists.**

### 2.4 Components and conductors
- **MLCC bias** [S, not re-verified]:
  - 0402/0603 X7R at 50–60% of rated V loses 30–50%; 1206/1210 lose 10–20%.
  - A 10 µF/6.3 V 0402 X5R behaves like ~1.5 µF at 5 V.
  - Start at 50% voltage derating. Delivered C can be 30–70% low ([Octopart](https://octopart.com/pulse/p/breaking-down-mlcc-surprises); [Ultra Librarian](https://www.ultralibrarian.com/2026/03/05/mlcc-capacitor-selection-ulc)).
- **Ferrite beads** ([Analog Dialogue 50-02](https://www.analog.com/media/en/analog-dialogue/volume-50/number-1/articles/ferrite-beads-demystified.pdf) [P, VERIFIED]):
  - Run at ~20% of rated current. At 50%, L falls by up to 90%; the TDK MPZ1608S101A goes from 100 Ω to 10 Ω at 100 MHz.
  - Bead + 10 nF peaked at ~2.5 MHz: **+10 dB** at a 2.4 MHz ripple.
  - Damping (ADP5071): (A) series 10 Ω in the cap path, which degrades HF bypass; (B) 10 Ω across the bead; (C) 1 µF + 2 Ω.
  - Weir: >30–40% of rating → L down 50%+ ([slides](https://emcfastpass.com/wp-content/uploads/2017/04/PDN_Ferrite_Beads.pdf)).
  - MT-101: 0.1 µF + 1 nH resonates at 16 MHz; damp with ~10 Ω in the line or a bead (resistive above 100 kHz).
- **Traces:**
  - IPC-2221: I = k·ΔT^0.44·A^0.725 (k 0.048 external / 0.024 internal). 1 A, 10 °C, 1 oz external → 16.3 mil² → **0.30 mm** (VR arithmetic VERIFIED; blog "20 mil" is wrong).
  - IPC-2152 (charts) usually allows more current; planes within ~0.5–1 mm act as heatsinks ([semiconductor.tools](https://semiconductor.tools/blogs/07-ipc-2221-vs-ipc-2152) [S]).
  - Rohm design values: >1 mm/A at 1 oz, >0.7 mm/A at 2 oz; 2 A → 0.53 mm for a 20 °C rise.
- **Vias:**
  - Calculators: 0.3 mm via ≈1.9 A with 25 µm plating, 1.6 A with 20 µm; others say 0.8–1.0 A; ~1.1 mΩ per via in 1.6 mm board; plating matters more than drill [S].
  - SLVA959 IPC-2152 (1 oz, 10 °C): 6 mil 0.2 A; 8 mil 0.55; 10 mil 0.81; 12 mil 0.84; 16 mil 1.1.
  - SLAA896 filled vias (R mΩ / L nH / I A): 4 mil 2.9/1.61/1.4; 6 mil 2.1/1.48/1.53; 10 mil 1.3/1.32/2.01; 12 mil 1.1/1.26/2.21; 18 mil 0.7/1.14/2.72.
  - **Default to SLVA959.**
- **Return stitching (PDN-08):**
  - TI: GND via "within 200 mil, closer is better"; Gen5 50 mil; EMA ≥2 vias within 100–200 mil. The 1 mm / 50 mil blog figures are secondary.
  - Stitching caps: **≤1 µF at split crossings** (VR CORRECTED the 1–10 nF claim).

### 2.5 PDN workflow (RPA §17; code, not LLM judgement)
1. **Rails** from BOM and datasheets: V, ΔV, I_transient (or I_max × activity), band. Z_t = fraction·ΔV/I.
2. **Lumped model:** VRM as R+L; MLCCs with bias-derated C (SimSurfing/K-SIM or a table), ESR and ESL; geometric mounting L; plane C = εA/d plus spreading L.
3. **Check:** |Z| ≤ Z_t across the band; peaks ≤1.57×Z_t (hard) / ≤3× (soft); report Q per peak; warn on ≥2 peaks with Q > ~2.
4. **Fix:** same-value caps (lower ESL), ESR damping, controlled-ESR bulk (C ≈ L/R²); not decade values.
5. **Cavity modes:** flag harmonics within ±10% of a mode; stitch and decouple at the mode maxima (edges and corners).

**Rules:**
- PDN-01: cap per power pin, vias at the pads; ≤2–3 mm, via-to-pad ≤0.5 mm [heuristic].
- PDN-02: rank caps by mounting L; bulk within 10–20 mm.
- PDN-03: tight plane pair.
- PDN-04: caps chosen from Z_t.
- PDN-05: derate before counting.
- PDN-06: bead ≤20% rated; f_res = 1/(2π√(LC)) not within ±50% of f_sw.
- PDN-07: IPC sizing + IR drop (ρ_Cu 1.72e-8 Ω·m, 1 oz = 35 µm).
- PDN-08: no plane cuts under signals; stitch at layer changes.
- PDN-09: peak limit.
- PDN-10: Q ≲ 1–2.
- PDN-11: cavity check.
- PDN-12: plane pairs high in the stack, thin, without necks.

### Implications for our system
- **Build an open-source lumped-RLC PDN screener** fed with geometric mounting L. It doesn't exist yet, so it's a differentiator.
- **"Lowest mounting L closest" ranking;** alternate orientation in clusters.
- **Pre-layout BOM checks:** bias derating, bead current, bead resonance vs f_sw.
- **Conservative via ampacity,** with the conflict logged.

---

## 3. RF

### 3.1 Findings
- **Module/IC datasheet geometry is primary:** 50 Ω CPWG over continuous ground, matching at the pin, keep-out polygon from the module figure.
- **u-blox** [P] ([NORA-B2](https://content.u-blox.com/sites/default/files/documents/NORA-B2-u-connectXpress_SIM_UBXDOC-465451970-3906.pdf); [MAX-M5Q](https://content.u-blox.com/sites/default/files/MAX-M5Q_HardwareIntegrationManual_(UBX-13002460).pdf)):
  - Geometry:
    - width ≥200 µm; trace-to-ground ≥2× width; arcs, otherwise 45°;
    - use the CPW model if the same-layer gap is ≤5× width;
    - 50 Ω FR-4 microstrip width ≈ 2× dielectric thickness;
    - ≥3W from the GND-plane edge.
  - Under and around the module:
    - U.FL pad voided on ≥1 inner layer;
    - no RF under the module or receiver (GND only ~100 µm away, tolerances to 100%); no ground cuts under the module;
    - "No digital routing … beneath all layers of RF traces";
    - MAX-M5Q: area under the receiver fully masked, no open vias.
  - Ground plane, enclosure and metal:
    - ≥10 mm ground beyond the module applies **only to the NORA-B2x6 embedded-antenna variant**;
    - plane ≥24×30 mm, >50×50 not recommended (embedded antenna);
    - metal ≥10 mm from the antenna.
  - Routing priorities:
    - minimise RF length first, then bus length;
    - "All traces, including low speed or DC traces, must couple with a reference plane";
    - power through bypass and bulk caps before the module pin;
    - stitched edge ground ring, power planes pulled back.
- **Nordic nRF52832** ([PS v1.0](https://cdn.sparkfun.com/datasheets/Wireless/Bluetooth/nRF52832_PS_v1.0.pdf) [P]):
  - The radio is not 50 Ω; the matching network also filters the 2nd/3rd harmonics.
  - Shunt C3 is grounded via **VSS pin 31**, not the plane (harmonic filtering).
  - Inner-layer keep-out under the match; ≥1 via per VSS pin.
  - ≥2 layers with a ground plane; VSS directly to a topside RF ground.
  - Separate filtered supply; fast digital away from the crystal and supply.
  - Reference layout has no bottom-side parts.
  - DevZone [S]: continuous ground under the centre pad and RF path; no plane under the antenna.
  - Use the reference design (QFN vs WLCSP matching differs). The 4×4 via grid was NOT RETRIEVABLE.
- **Espressif ESP32** ([guide](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html) [P]):
  - Antenna and board:
    - antenna at or beyond the edge; cut the board beside and below it; never mid-board with four-side cut-outs;
    - 15 mm = enclosure clearance;
    - keep the antenna away from crystals, DDR, HF clocks, USB and UART.
  - Stackup and power:
    - L1 signals; L2 solid GND; L3 power + some signals, GND under RF and crystal; L4 few signals, no parts;
    - power traces ≥25 mil (main), ≥20 mil (VDD3P3), 12–15 mil others; ≥2 vias on main-power layer changes;
    - ground pad ≥9 vias.
  - RF path:
    - CLC match in 0201 "zigzag" at the pin;
    - 15 mil, 100 Ω ±10% 2nd-harmonic stub on the shunt-cap ground pad (not needed for 0402+);
    - outer layer, no vias, constant width, no branches; all layers clear under IPEX; 2-layer RF trace >20 mil.
  - Other limits:
    - SDIO ±50 mil, 50 Ω ±10%, ≤2000 mil;
    - touch traces ≤300 mm, ≤0.18 mm wide, 0.5–1 mm gap, electrodes 8–15 mm;
    - ripple <80 mV (MCS7 at 11n), <120 mV (11b).
- **Separation and shielding** (RF Essentials/AtlasPCB, low):
  - ~20 mm from SMPS; LNA input far from SMPS.
  - Can ring 0.5–1.0 mm with vias ≤1.0 mm apart; fence ≥3× substrate height from the trace.
  - Double staggered rows for TX/RX; 30–70 dB shielding (rough).
- **Via fences:** pitch < λ_g/20 ([Wikipedia](https://en.wikipedia.org/wiki/Via_fence)); single-via self-resonance at a few hundred MHz to a few GHz. At 77 GHz, λ/20 ≈ 0.1 mm → microvias ([AtlasPCB](https://www.atlaspcb.com/blog/gcpw-coplanar-waveguide-pcb-design-rf-mmwave/), low).
  - Worked values [D] (εr 4.3, conservative for microstrip): 2.4 GHz λ_g ≈60 mm → λ/20 ≈3.0 mm, λ/10 ≈6 mm; 5.8 GHz ≈1.25 mm; 1 GHz ≈7.2 mm.
  - With u-blox's 2 mm unsourced, λ/20 at the highest harmonic of concern is the **soft** default.
- **Bends:**
  - The 90° myth comes from a 1971 MECL figure. A 5-mil corner (8.5 fF) has no effect until >70 GHz (Bogatin). Johnson: fine to 2 Gbps, starting to matter at 10 Gbps.
  - Miter: 20 dB at 77 GHz (simulation); maybe worthwhile from ~5.8 GHz ([Altium](https://resources.altium.com/p/slaying-900-right-angle-bend-dragon); [GaTech](https://tentzeris.ece.gatech.edu/ECTC09_Rida.pdf)).
  - RF: arcs or 135°. Acute angles are an acid trap.
- **Rules:**
  - RF-01: Z0 from a solver; continuous reference.
  - RF-02: point-to-point, no stubs or test pads (stub ≪λ/10).
  - RF-03: first match ≤~1 mm [heuristic]; shunt at the named pin. **HARD topology.**
  - RF-04: fence ≤λ_g/20. Soft.
  - RF-05: **split into** a HARD PCB keep-out from the module figure + an enclosure clearance on the mechanical checklist.
  - RF-06: separation. Soft.
  - RF-07: only GND under RF. **HARD.**
  - RF-08: arcs above a few GHz (S3 >5 GHz, S4 <1 GHz); acute angles banned.
  - RF-09: pour stitching ≤λ/20 (λ/10 looser). Perimeter stitching is CONTESTED: Hubing says perimeter-only stitching can form a resonant cavity, Ott says stitch the periphery.

### Implications for our system
- **Store RF data per part, never generalised:** keep-outs, stacks, stubs, power widths. Extract keep-out polygons from figures (vision + human review).
- **Antenna keep-out:** an all-layer KiCad rule area (no tracks, vias or zones). Enclosure clearance goes in a mechanical report.
- **`RF50` net class:** solver width/gap, point-to-point topology, arc corners, fence and stitching scores, reference-integrity raster.
- **SMPS distance as a ranked objective;** prefer fences or cans when dense.

---

## 4. Analog, mixed-signal, precision sensing, crystals

### 4.1 Grounding
- **One solid plane, partitioned placement, ADCs straddling** ([Ott](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html) [P]; [TI SLYT512](https://www.ti.com/lit/an/slyt512/slyt512.pdf)). If split: one bridge, all crossings over it.
- **Ott:**
  - LSB at 1 V: 8 bit 4 mV; 10 bit 1 mV; 12 bit 240 µV; 14 bit 60 µV; 16 bit 15 µV; 20 bit 1 µV; 24 bit 60 nV. Keep ground noise below the smallest signal.
  - 8–12 bits: one partitioned plane "usually adequate".
  - ≥14 bits: isolated regions, each tied under each ADC, **no trace on any layer crossing the slots**.
  - Jumper test: links every ½"; "in almost all cases … better with the single ground plane".
  - On datasheet AGND+DGND advice: where does digital decoupling return? Use one plane.
- **ADI MT-031** ([MT-031](https://www.analog.com/media/en/training-seminars/tutorials/MT-031.pdf) [P]):
  - Low-digital-current converters are analog parts; tie AGND and DGND to the analog plane with minimum length. DGND to a digital plane "invites disaster"; Bryant: "even if the data sheet suggests otherwise".
  - VD decoupling 0.01–0.1 µF to DGND, optional lossy bead.
  - Buffer register at the outputs with series R (500 Ω × 10 pF → 11 ns).
  - ~0.2 pF between any two package pins.
  - >300 mV between separate planes → damage or latch-up; back-to-back Schottkys at the star.
- **TI SLYT499:** AGND/DGND to one low-impedance plane. ADI EZ: multi-device parts such as AD5522 specify their own scheme.
- **Hubing:** "more than one ground" is MOST EGREGIOUS; ground islands under ICs are "a bad idea".
- **Altium/Peterson:** below ~100 kHz, returns spread resistively; engineer return paths and star the power entry (§6.6).
- **Pease** ([Lab Notes](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/1023/Bob-Pease-Lab-Notes-Part-7.pdf) [P]): for high isolation, build the boards separately or put analog in a shield box with copper fences. 35 dB is feasible; 50 dB takes "all those extreme efforts".

### 4.2 Op-amps, guards, symmetry
- **Guards** ([TI AN-241](https://www.ti.com/lit/an/snoa664/snoa664.pdf) [P]):
  - Driven from a low impedance at input potential: +IN for inverting configurations, −IN for non-inverting.
  - Both sides. Surface leakage "virtually eliminated"; bulk leakage down "about an order of magnitude" with double-sided guards.
  - Mask-free guard unverified.
- **Summing node** is the most parasitic-sensitive ([Op Amps for Everyone](https://web.mit.edu/6.101/www/reference/op_amps_everyone.pdf)). Williams: 1 pF across 1 kΩ caused severe peaking; "Consider layout as an integral part of the circuit."
- **Thermal EMF:** ~200 nV/°C; symmetric isothermal layout (low). Pease: ">50 rules" for matching; common-centroid "very easy, using the rules of symmetry".
- **Rules:** AMS-01 plane partition; AMS-02 AGND/DGND at the package; AMS-03 one bridge; AMS-04 converter decoupling to AGND plus a buffered interface; AMS-05 guards; AMS-06 summing node ≤~3 mm [heuristic]; AMS-07 symmetric, away from heat; AMS-08 crystals; AMS-09 Kelvin everywhere.

### 4.3 Sensor front ends (the dominant error picks the rules)
- **Thermocouple** ([SBAA274](https://www.ti.com/lit/pdf/sbaa274) [P]):
  - Every metal joint is a junction, so keep connections "simple and symmetric".
  - Isothermal CJ block: a massive connector or layered copper fill. CJ sensor error passes straight through. Shield from air currents.
  - Seebeck (µV/°C): J 50.37, K 39.48, T 38.74, E 58.70.
  - SEN-01: CJ sensor on the connector island; TC± symmetric (layer, vias). SEN-02: heat ≥15–20 mm away from >0.5 W parts [heuristic].
- **Bridge** ([SBAA532A](https://www.ti.com/lit/an/sbaa532a/sbaa532a.pdf); [TIDUB00](https://www.ti.com/lit/pdf/tidub00) [P]):
  - 6-wire Kelvin; excitation drives V_REF (ratiometric).
  - Parasitic thermocouples and bias current × lead R cause offset; AC excitation cancels it.
  - Traces "short and balanced"; terminal block near the input resistors; R_G at the pins.
  - SEN-03.
- **TIA: opposite regimes (SEN-04).**
  - High-speed: pour removed around IN− "on both layers"; C_F needed; 49.9 Ω + 50 Ω microstrip out ([TIDU535](https://www.ti.com/lit/pdf/tidu535)).
  - fA–pA: guarded and "well shielded"; resistors carry ~0.5 pF; C0G, polycarbonate, polystyrene or silver mica caps ([SBOA034](https://www.ti.com/lit/an/sboa034/sboa034.pdf)); guard TH cathode pins on the bottom (E2E [S]).
  - Thresholds [D]: BW ≳100 kHz with R_F ≲1 MΩ vs R_F ≳100 MΩ.
  - SEN-05: R_F∥C_F across IN−/OUT, minimal IN− copper.
- **SEN-06:** ADC resolution in the BOM selects the partition strategy.

### 4.4 Crystals (RPA §4 + IRP §7 + VR)
- **ST AN2867** ([Rev 19](https://ecsxtal.com/store/pdf/stm32-microcontroller-application-note.pdf) [P, VERIFIED]):
  - Closest possible; grounded guard "essential"; dedicated oscillator ground to the nearest MCU ground.
  - **Metal can not to oscillator ground.**
  - Symmetric caps; coat LSE in humidity.
  - Faults listed include "too many test points" and "no symmetry".
  - C_s = pin + PCB; gain margin >5; PC13 toggling shifts the LSE.
  - 0.175 pF × 45 ppm/pF ≈ 7.8 ppm; LSE C_L ≥6 pF (7 pF compromise).
  - No mm values.
- **Microchip dsPIC33AK** [P]: ≤½ in (12 mm), same side, caps adjacent; grounded pour with no signal or power inside; nothing under the crystal on the far side; tie broken guards to a mirrored ground.
- **Espressif:** crystal **≥2.7 mm** (ESP32) / 2.0 mm (S3) from the clock pin (a lower bound); no clock-trace vias; dense ground vias; series parts at the chip; caps on both sides; nothing under the crystal; no magnetics near; top keep-out ring when ground suffices.
- **Parasitics:**
  - AVR186: XIN–GND 1 pF, XOUT–GND 2 pF, XIN–XOUT 0.5 pF. AN826: 2–5 pF total.
  - TUSB9261: C_SHUNT 4.5 pF, 20 pF load.
  - AN-1469: C_L1 ≈ 2C_L − 7 pF (start 33 pF).
  - SWRA495L: 2–3 pF internal + 7 pF = 9 pF; 802.15.4 ±40 ppm.
- **Other vendors:**
  - AVR186: XIN cap first; C0G; XIN/XOUT apart; cap grounds clear of USB, RS-232, LIN, PWM and power returns.
  - SLAA322D: never route ground between the caps or around the crystal; guard to AVSS only.
  - Qualcomm: C-shaped GND-via ring at clock and RF transitions.
- **Conflicts:**
  - Metal can: ST no; TI and AVR yes.
  - TUSB9261: VSSOSC off the plane.
  - Copper under the crystal: solid ground (most) vs cut planes (CDCE925 [S]).
  - Digest note: ST's oscillator ground island vs Hubing's island anti-rule.
- **Packs:** XTAL-DMAX/DMIN/SIDE/CAP/PAR/SEP/GUARD/SER/MAG/CAN/TP. Placement is an annulus, vendor minimum ≤ d ≤ 12 mm, scored by trace C = length × C′. RPA's ≤5 mm is a heuristic.

### Implications for our system
- **Rule-selected ground strategy.** ADC bits plus datasheet mandates pick the strategy, which activates the matching checks (slot crossings, tie count, 300 mV).
- **Classify the TIA regime before applying any copper rule.**
- **Matched-pair mirror metrics** and isotherm distances.
- **Crystal pack:** distance window, pF budget, guard rule area, 0 test points, vendor switches.

---

## 5. Isolation, creepage, clearance, HV safety

**Method** (TI SLUP419 [P] ([PDF](https://www.ti.com/lit/pdf/slup419))):
- Grade from the end-product standard.
- Creepage = f(V_RMS, PD, material group by CTI), ×2 for reinforced.
- Clearance = f(impulse voltage from mains V × OVC, PD, altitude); reinforced = one impulse step up (or IEC 62368-1 Table 10 reinforced column); ×Table A.2 factor above 2000 m.
- Tables: IEC 60664-1 F.4; 62368-1 Table 17 (AV/ICT); 61800-5-1 Table 10 (drives); 62109-1 Table 14 (solar).
- **IPC-2221B and IPC-9592B are "functional … not user safety".** Coating can lower PD (IEC 60664-3), or use 62368-1 Table G.13.

**Lookup tables (SLUP419 subsets):**
- Material groups: I ≥600; II 400–600; IIIa 175–400; IIIb 100–175. TI isolators are group I; FR-4 is III/IIIa.
- PD1 dry/coated; PD2 occasional condensation (offices, labs, servers); PD3 conductive (industrial); PD4 continuous (outdoor). OVC I (protected) to IV (installation origin).
- F.4 creepage (mm):

  | V_RMS | PD1 | PD2 group I | PD2 group II | PD2 group III |
  |---|---|---|---|---|
  | 63 | 0.2 | 0.63 | 0.9 | 1.25 |
  | 400 | 1.0 | 2.0 | 2.8 | 4.0 |
  | 800 | 2.4 | 4.0 | 5.6 | 8.0 |
  | 1000 | 3.2 | 5.0 | 7.1 | 10.0 |

  RPA's 250 V ≈2.5 mm (group III) is from memory; verify it.
- F.1 impulse (V, OVC I/II/III/IV): ≤50 V 330/500/800/1500; ≤150 V 800/1500/2500/4000; ≤300 V 1500/2500/4000/6000; ≤600 V 2500/4000/6000/8000.
- F.2 clearance (62368 Table 10 in parentheses): 0.5 kV 0.04/0.2/0.8 mm (PD1/2/3); 1.5 kV 0.5 (0.76), PD3 0.8; 2.5 kV 1.5 (1.8); 4 kV 3.0 (3.8); 6 kV 5.5 (7.9).
- Example (265 V, OVC II, PD2, 5000 m, reinforced): creepage 4/5.6/8 mm (MG I/II/III); clearance 3.6 × 1.48 = 5.33 mm.

**When spacing cannot be met:**
- Slots add creepage, not clearance. Minimum width 0.25 (PD1) / **1.0 (PD2)** / 1.5 mm (PD3).
- Coating helps clearance.
- Functional isolation only: hi-pot at 2V_w + 1000 V (265 VAC → 1530 V).
- **Trap:** group-I package (4 mm) on a group-IIIa PCB (8 mm) → add a slot.

**Device guidance:**
- **TI SLLA284G** ([guide](https://www.ti.com/lit/pdf/slla284)): ≥4 layers (HS / GND / PWR / LS); **nothing under the isolator on any layer**; a groove >1 mm counts if creepage + width + 2×depth ≥ required; higher CTI allows a smaller package.
- **PI AN-72** ([PDF](https://www.power.com/sites/default/files/documents/an-72_innoswitch3_family_design_guide_20251107.pdf)): >8 mm primary↔secondary, especially under the IC and transformer; no traces under the IC; spark gaps (§0 values) from secondary terminals to one AC line after the fuse, plus one across the CM choke, never near the IC; 0.4 mm mylar under a heat spreader crossing the barrier.
- **BQ76952:** copper spark gaps (E-prefix), no part fitted.

**IPC-2221B Table 6-1** (functional floor): 31–50 V 0.1/0.6/0.6/0.13 mm (B1/B2/B3/B4); 301–500 V 0.25/2.5/12.5/0.8; >500 V per volt B1 0.0025, B2 0.005, B3 0.025, B4 0.00305 mm/V.
- B1 internal; B2 external uncoated (≤3050 m); B4 permanent polymer coating. **Solder mask is not B4.** Altitude derating applies. The JLCPCB blog table is an outlier.

**Rules:**
- ISO-01: classify net voltage and pair grade; a missing class is an error.
- ISO-02: surface-path creepage; slots narrower than the PD minimum don't count.
- ISO-03: 3-D clearance × altitude factor.
- ISO-04: all-layer barrier keep-out ≥ creepage under isolators, optos and the transformer span, with the slot centreline under the barrier.
- ISO-05: slot width.
- ISO-06: spark-gap footprints.
- ISO-07: Y-cap from primary bulk+ (or AC after the fuse) to secondary, never via controller ground.
- ISO-08: fuse first from the AC connector (general practice).

**Gaps:** mains filter, MOV/fuse placement, ES1/2/3 classes, Table G.13 values; KiCad surface-creepage DRC (reported for 9+, unverified).

### Implications for our system
- **Deterministic engine:** (V_RMS, impulse/OVC, PD, MG, altitude, grade) → (creepage, clearance).
- **Surface-geodesic creepage checker** (respecting valid slots) plus a 3-D clearance checker.
- **The LLM proposes classes and grades only; a human confirms.** Take the stricter of IPC-2221B and the safety standard.

---

## 6. Circuit-class specifics

### 6.1 Offline flyback (PI AN-72 [P])
- **Four tight loops; "No loop area should be placed inside another loop":**
  1. primary: bulk → winding → D/S;
  2. clamp: RCD, or ~200 V Zener + diode, away from the BYPASS pin;
  3. secondary: N_S, C_OUT, SR FET (copper on the SR FET, short SR-source→IC-GND);
  4. bias.
- **Grounds:** single point from the input cap to SOURCE copper; bias and SOURCE grounds separate, joined once; secondary star at R_IS with separate GND, C_OUT and FB traces; star at cap pads; no signal shares AC switching paths.
- **Placement:**
  - Bypass caps at their pins; R_LS, R_BP, R_FB and R_IS close to the pins.
  - **FB/VOUT taken before the post-filter L;** post filter at the terminals.
  - π-filter L in the **negative** leg.
- **Keep-outs:** quiet traces away from the drain, "underneath transformer belly", switching winding ends and the rectifier; minimal drain copper.
- **Rules:** FLY-01 loop sets; FLY-02 containment test; FLY-03 belly/drain keep-out (+1–2 mm); FLY-04 FB before L_post; FLY-05 one join per side; FLY-06 >8 mm + creepage engine.
- Only PI's guidance was read.

### 6.2 Motor drivers ([TI SLVA959B](https://www.ti.com/lit/pdf/slva959) [P])
- **Grounds:** single point for power, star for signals; partition, don't split; grid the ground on 2 layers; keep via clusters from splitting planes; isolate predriver ground, joined at the star.
- **Caps:**
  - Bulk >10 µF at the entry with multiple vias; ceramics <10 µF at each half-bridge.
  - Bypass on the IC layer, no via between cap and pin, "<0.5 cm (0.2 in)", L/W ≤3:1.
  - ~1 nF at the CSA pins; charge-pump and bootstrap caps at the driver.
- **Routing:**
  - Gate traces ≥20 mil at 1 oz; HS gate beside SW.
  - Teardrops; series parts side by side, not staggered.
  - Half-bridge "stack" or "side-by-side" with a short, wide HS-S→LS-D link; minimal layer jumps.
- **Sensing:**
  - Low-side shunt LS source→star; high-side near the star, first gain resistor at the shunt.
  - Tight pair with a **net tie**; never parallel to switching nets.
  - 20 A × 1 mΩ = 400 mW for 20 mV.
  - VDRAIN: one Kelvin trace + net tie (avoids false OCP).
- **Thermal:** continuous pours, 1.5–2 oz, direct-connect unmasked vias (20/8 mil); doubling copper halves lateral R.
- **Errors in SLVA959:** see §0; its "90° bends reflect" claim is not credible.
- **Rules:** MOT-01 commutation loop {C_byp, HS.D, LS.S} ≤~5 mm; MOT-02 SW L/W; MOT-03 gate pairs; MOT-04 shunt + ties; MOT-05 VDRAIN; MOT-06 bulk/HF placement; MOT-07 thermal pad.

### 6.3 LED drivers ([TPS922050](https://www.ti.com/lit/ds/symlink/tps922050.pdf) [P])
- Hot-loop rules by topology.
- CSP/CSN parallel, short, away from SW and the ground shield; R_FLT 100 Ω, optional 1 nF/50 V X7R C_FLT.
- "Do not allow switching current to flow under the device."
- COMP at its pin; large GND; thermal vias.
- LED-01…04, including keeping LED heat away from sense and reference parts. MCPCB not covered.

### 6.4 Chargers and BMS
- **BQ25895** ([DS](https://www.ti.com/lit/ds/symlink/bq25895.pdf)), where order "is essential":
  1. PMID cap;
  2. L at SW, minimal copper, **no paralleled layers**;
  3. COUT;
  4–5. AGND/PGND joined once under the IC (pad or 0 Ω), pour kept off the power pins;
  6. decoupling;
  7. EP vias;
  8. vias sized for current.

  PMID ≥8.2 µF; 40 µF (≤2.4 A) or 60 µF (≤3.1 A) with OTG.
- **BQ76952** ([DS](https://www.ti.com/lit/ds/symlink/bq76952.pdf)):
  - "Quality of the Kelvin connections … is critical"; TC ≤50 ppm; 1 mΩ; paralleled shunts OK.
  - 100 Ω + 0.1 µF filter **at the IC, not the shunt**, with parallel traces.
  - REG18 at its pin; Zener + R on I2C.
  - 2-layer reference (2.75×3.9 in): cells left, pack top, spark gaps.
- **Cell filters:** 20 Ω / 0.22 µF (1 µF OK), ≤100 Ω [S]. SLUAA81: 20 Ω minimum for internal balancing; FET ~25 Ω; balancing adds IR drop at VC16.
- **Rules:** CHG-01 order; CHG-02 single-layer SW (default for all bucks); BMS-01 Kelvin + filter at the IC; BMS-02 ordered, uncrossed cell traces, balance resistors spread from the monitor and NTCs; BMS-03 high-current path off the monitor ground; BMS-04 spacing from cell index × V (16S ≈67 V).

### 6.5 High current
- **JLCPCB min space by weight:** 1 oz 0.10; 2 oz 0.16/0.15; 2.5 oz 0.20; 3.5 oz 0.25; 4.5 oz 0.30 mm.
- **SNVA419:** ≥1 oz; 2 oz above 3 W; 4 oz above 6 W.
- **SLAA896** (width → mΩ/in, A): 30 mil 9.68, 3.18; 40 mil 7.08, 3.63; 50 mil 5.58, 4.32; 80 mil 3.41, 5.55.
- **Würth PowerBusbar** [P]: one-step press-fit, order element → PCB → busbar; replaces heavy copper or inlays; capacity is system-dependent; IPC-A-600 + Würth spec. [S]: bar 1.0–1.5 mm; PCB ≤2.0 mm; 60–350 N per pin, retention 60–80%; transitions 100–200 µΩ, which with the layout are usually the limit.
- **Laminated** supply/return cuts L (low).
- **Rules:** HC-01 narrowest cross-section; HC-02 ceil(I/I_via) vias at pads (0.8 A default); HC-03 weight vs min-space; HC-04 overlapped return; HC-05 busbar keep-outs; HC-06 Kelvin.

### 6.6 Audio and class-D
- **SLAA896** ([PDF](https://www.ti.com/lit/pdf/slaa896)):
  - 4–6 layers, filled vias; ground balls tied on top and stitched to L2.
  - Smallest cap **<1 mm** from the pin.
  - **Budgets (pin-to-pin + 500 pH ESL):** DREG–GND 650→1150 pH; GREG–PVDD 300→800; VBAT–GND 650→1150; VBST–BGND 250→750; VDD–GND 350→850.
  - No adjacent-layer coupling for OUT/SW/Vsense without GND between.
  - Boost SW 5 A.
  - Vsense 6 mil differential from the speaker terminals.
  - VBST–PVDD strap under the device.
  - Supplies starred at 20–30 mil; charge-pump cap starred at PVDD.
- **TPA3110D2** [P]: IC centred on the plane; PowerPAD vias 0.33 mm at 1.0 mm; HF caps ≤1 mm; snubbers and filters at the IC; outputs at the filter-cap pads; quiet-side inputs with floods; AGND to the PowerPAD.
- **Others:** SLYT182 [S] (continuous plane); EE Times [S] (small filter loop).
- **Rules:** AUD-01 (loop-L budget, reusable for any part that publishes one); AUD-02; AUD-03; AUD-04; AUD-05 (flag shared ground copper between power returns and audio references).
- **Gap:** pin-1 problem, cable shields.

### Implications for our system
- **Each class becomes a pack:** detector → roles → loops → constraints, with datasheet order as `placement_priority`.
- **Generator-inserted net ties enforce Kelvin connections.**
- **pH budgets** become estimator targets.

---

## 7. Thermal method

- **R_θJA is a JEDEC-board property** ([SPRA953D](https://www.ti.com/lit/pdf/spra953) [P]):
  - 70–95% of the heat leaves through the board.
  - Influence: PCB 100%, chip/pad 50%, package 35%, altitude 18%, ambient 7%, power 3%.
  - 1s vs 2s2p shifts R_θJA up to 50%.
  - Ψ_JT 0.5–2 vs R_θJC 4–15 °C/W; T_J = T_top + Ψ_JT·P. Use Ψ_JB with a board thermocouple; no Ψ_JT with a heatsink.
- **SNVA419C** ([PDF](https://www.ti.com/lit/pdf/snva419) [P]):
  - Rule 1: ≥15.29 cm² (2.37 in²) of two-sided copper per W for a 40 °C rise in still air (airflow up to halves it), or area ≥ 500/(θ_JA − θ_JC) cm². Assumes the EP reaches planes extending to the edge. Inner planes give up to 30% better.
  - Rule 2: ~261 °C/W per 12 mil, 0.5 oz via; as many as fit at 1 mm, on all layers.
  - Rule 3: copper by power; 28.3 → 21.2 °C/W for 1 → 2 oz.
  - Rule 4: perpendicular cut 5.5 °C vs parallel 1.5 °C; route radially.
  - Rule 5: bottom heatsink (θ_JT 50–200 °C/W).
  - Rule 6: superposition "almost works".
  - Constants: λ_Cu 4, FR-4 0.0023 W/cm·K; h ≈ 10 W/m²K; 1 cm² of 1 oz lateral ≈71 °C/W; FR-4 vertical per cm² ≈13.9 °C/W.
- **SLMA002H:** TQFP land ≤ body − 2.0 mm (mask-defined); 5–9 vias suffice for a small die; 0.33 mm, 1 oz barrels ≈1% of land; never unsoldered.
- **EP vias and assembly:**
  - SLOA122: 0.3 mm at 1 mm; don't mask; no spokes; plugging unneeded.
  - SLUA271C: ~1.0 mm pitch; tent 0.1 mm larger.
  - TB389: 1.0–1.2 mm pitch, 0.3–0.33 mm, ~1 oz barrel; tent from the top.
  - Rohm: 0.3 mm at 1.2 mm. MPS: 10/20 mil.
  - TPS62130: vias under paste filled, plugged or tented.
- **Paste and voids:** paste 50–70% (TI) / 50–80% (Renesas, Maxim); 1:1 apertures float the part; void limit 25% vs 50% (TI).
- **Blog numbers:** ~150 °C/W per 0.3 mm/25 µm via; 9 vias ≈17–33 °C/W; filled vias 6–8× better (claim). Stackups are anisotropic, so build 3-D paths ([Salitronic](https://salitronic.com/kb/thermal-management/)).
- **Placement (low–medium authority):**
  - Tall parts upstream create a wake (a 10 mm electrolytic was cited). Sensitive parts upstream; tall parts aligned with airflow.
  - Hot parts 5–10 mm apart (two 2 W parts 5 mm apart add); out of corners.
  - Electrolytic life halves per 10 °C (simplified; polymer differs; +35 °C near IGBTs example) ([CapXon](https://www.capxongroup.com/files/Lifetime%20Compendium_EN.pdf)).
  - 2 in² of copper −10–15 °C (illustrative).

**Screening estimator (RPA §18):**
1. Power: LDO (V_IN − V_OUT)I; switcher P_out(1/η − 1), split IC/L/D; I²R; LED (1 − η)P.
2. Spreading area by zone-graph flood fill from the EP, clipped by lateral R.
3. R_J-pad + 261/N + L/(λWt) + 1/(hA, both sides).
4. Superpose.
5. T_J < T_J,max − margin; sensitive parts within limits and small ΔT.

**Rules:**
- TH-01: EP array, count ≈ EP area / pitch², for P ≳0.3 W.
- TH-02: tent/plug.
- TH-03: paste.
- TH-04: copper from P.
- TH-05: spread hot parts.
- TH-06: sensitive parts ≥10 mm away and upstream.
- TH-07: airflow cone.
- TH-08: no SW heatsinking.
- TH-09: never R_θJA alone.
- TH-10: 15.3 cm²/W.
- TH-11: 1 mm pitch, direct connect.
- TH-12: copper weight.
- TH-13: no perpendicular cuts.
- TH-14: bottom heatsink.

### Implications for our system
- **First-order estimator in the placement loop** (not FEA, as SNVA419 itself says).
- **The LLM extracts I, η and θ; code computes.**
- **Aggressor/victim classes feed the criticality map.**

---

## 8. DFM/DFA and fab limits

**Fab profiles** (official pages; mm):

| Parameter | JLC 2L rec/abs | JLC ML | PCBWay | OSH 2L | OSH 4L |
|---|---|---|---|---|---|
| Trace/space 1 oz | 0.10 | 0.09 (3 mil BGA fan-out) | 0.10 | 0.152 | 0.127 |
| Drill | 0.2 pref/0.15 | same | 0.15 (≥0.2 no surcharge) | 0.254 | 0.254 |
| Annular ring | 0.25/0.18 | 0.20/0.15 | 0.15 | 0.127 | 0.102 |
| Cu to routed edge | 0.2 | 0.2 | 0.20–0.25 | 0.381 | 0.381 |
| Cu to V-cut | 0.4 | 0.4 | — | — | — |
| Silk line/text | 0.15/1.0 | same | 0.15/0.8 (1:5) | 0.127 (0.076) | same |

**JLCPCB extras** [P]:
- Weights: 2L 1/2/2.5/3.5/4.5 oz; ML outer 1–2 oz, inner 0.5 oz. Tolerance ±20%. 2 oz annular ring ≥0.254; NPTH ring ≥0.45.
- Vias ≥0.15/0.25 (0.1/0.2 only ≤1 mm ENIG/OSP); pad = hole + 0.1 (0.15 preferred); preferred hole 0.2.
- Hole-to-hole: via 0.2, pad 0.45.
- Clearances: pad–track 0.1 (0.09 BGA); SMD pad–pad 0.15; min pad 0.25²; via–track 0.2; PTH–track 0.28 (0.35 recommended); NPTH–track 0.2; inner via 0.2 / PTH 0.3; mask bridge 0.10 (0.13 black/white).
- Plugged vias ≤0.5 mm, 0.35 mm from openings. **BGA via-in-pad must be filled and plated.**
- Edges and panels:
  - routed edge ±0.2 (±0.1); V-cut ±0.4 at 25°, V-cuts ≥2 mm apart (3 recommended);
  - mouse-bite spacing 1.6/2 mm; tooling edge ≥3 mm;
  - SMT panels: 5 mm rails, 2 mm holes, 1 mm fiducials at 3.85 mm.
- Castellations ≥0.5 mm, 1 mm from the edge.
- Impedance ±10% (±5%). Dk 4.5 (2L), 7628 4.4, 3313 4.1, 2116 4.16. Backdrill on 4–32 layers, ≥0.8 mm.
- Assembly: pitch 0.35 (standard) / 0.40 (economic); BGA 0.3/0.5; 01005; panel ≤250×250; part-to-outline 0.2/0.4 [S].

**Others:** PCBWay hole tolerance ±0.08/±0.05, half-holes ≥0.4, panel gap 1.6 (routing) / 0 (V-score). OSH 4L FR408HR, 7.87 mil prepreg; no blind, buried or filled vias. Eurocircuits inner isolation = IAR + 0.075 (≥0.200); NPTH ring ≥0.30. Official pages beat blog numbers.

**Assembly and mechanical:**
- **Courtyards:** IPC-7351 A 0.50 / **B 0.25** / C 0.10 mm per side (fillet goals, not quality classes); B gives ≥0.5 mm land-to-land. Hausherr: users run 0.10/0.20/0.40, and Siemens, Cadence and Zuken users switch excess off ([PCB Libraries](https://www.pcblibraries.com/forum/placement-courtyard-excess_topic3372.html)). [S]: 1.0 mm around BGAs, ~1.5 mm rework; Cadence 0.25–0.3 mm side-to-side, 0.5–1 mm to edge; TI ≥0.508 mm between lands.
- **Tombstoning** (0201/0402) [S]: symmetric pads; relief spokes 0.10–0.20 / gaps 0.20–0.30 mm; mirror vias within 1 mm; balanced paste; longer soak.
- **Fiducials:** 1–3 mm; clear area ≥ radius (diameter preferred); edge ≥7.62 mm SMEMA + clearance; local fiducials at ≤0.5 mm pitch (others <1.0 / ≤0.4); 3 global in an asymmetric L, same size ([Solutions Mfg](https://www.solutionsmfg.com/images/pdf/fiducial.pdf)).
- **Test points:** 0.100" pitch (0.050" minimum); ~0.035" pads; 0.125" from the edge; 0.040" from parts (handlers 0.138") ([Test Electronics](https://testelectronics.com/info/whitepapers/dft.php)). Flying probe [S]: 0.5/0.75 mm pads, 60/80 mil pitch. One side.
- **Depaneling** [S]: ≥2 mm from the V-cut; MLCCs 3–5 mm (5 mm on 0.8 mm boards), because flex cracks pass test then fail; soft-termination parts near edges. Stress from lowest: push-back < slit < V-groove < perforation.
- **Panels** [S]: rails 5–10 mm; tooling 2–4 mm NPTH, asymmetric, ≥2 mm clear; bites 0.5–1.0 mm, tabs 2–3 mm every 50–90 mm; parts 1.5–2.5 mm from tabs.
- **Orientation:** one direction, 0/90°; clear pin-1 marks; avoid THT ([Cadence](https://resources.pcb.cadence.com/home/2024-dfa-guidelines-for-pcb)). FEDEVEL: extra connector and slot silk.
- **Mounting holes** (no standard): RP2040 NPTH 2.75 mm, mask 3.15, **keep-out 6 mm** (others 2.7/5.8/6.2); ISO 273 M3 3.2/3.4/3.6 [S]; M3 head ≈5.5 mm, ~7 mm used [S]; TI: no HS traces near holes.

**Rules:**
- DFM-01: DRC = absolute, router = recommended + margin; edge copper 0.3–0.5 mm preferred.
- DFM-02: courtyards.
- DFM-03: tombstone ratio >~2 flags.
- DFM-04: ≤2 orientations per polarized class.
- DFM-05: single-sided SMT; light parts only on the bottom; no THT under SMD.
- DFM-06: fiducials.
- DFM-07: test points.
- DFM-08: edge/V-score by class.
- DFM-09: hole keep-out.
- DFM-10: HV.
- DFM-11: silk.
- DFM-12: 3-D height.

### Implications for our system
- **Fab packs** (precedence 10) set `min` only; `recommended` becomes the router's `opt`. Other packs can never relax them.
- **Copper weight feeds pad-gap checks.**
- **Hole keep-out** Ø = max(head/standoff + 2×0.5 mm, vendor example).
- **Most limits are native KiCad DRC.** Tombstone, fiducial/test-point coverage and class-based edge distances need Python.

---

## 9. Expert placement methodology

**Order (RPA §7)**, from constraint rigidity ([EMA](https://www.ema-eda.com/ema-resources/blog/best-practices-for-pcb-component-placement-emd/); [Sierra](https://www.protoexpress.com/kb/pcb-component-placement-rules/)). Altium's "90% placement / 10% routing" is self-described as debatable.
1. **Mechanical:** outline, holes, edge connectors, UI parts, height zones, antenna edge + keep-outs; lock them.
2. **Stack-up and plane plan:** GND under critical circuits; rails; regions; I/O at connectors.
3. **Anchor ICs**, oriented to minimise crossings; reserve fan-out; BGA central ([PCBWay](https://www.pcbway.com/blog/PCB_Design_Layout/BGA_PCB_Layout_Guidelines_Placement_Fanout_and_Routing_b8eeabdd.html)). Fan-out: dog-bone ≥0.8 mm pitch, via-in-pad ≤0.65 mm; outer rows on top; power and ground first ([AtlasPCB](https://www.atlaspcb.com/blog/bga-fanout-routing-strategies-dog-bone-via-in-pad/)).
4. **Critical templates:** converter, crystal, RF, ADC/reference, shunts.
5. **Decoupling.**
6. **Signal flow:** connector → ESD → filter → transceiver → IC; hierarchy sheets as clusters.
7. **DFM pass.**
8. **Route:** hot loops/RF → sensitive analog → clocks/HS → general → pours/stitching → checks.

Score placement before routing (ratsnest, crossings, congestion, violations).

**Practitioners (RPA §19):**
- **Feranec** [P-sec]:
  - Big parts first; room between MPU and DDR; high-current parts far away.
  - Decoupling under the BGA; terminations at the driver; ESD/EMI at the connector; 3-D models.
  - Power fan-out with 0.3 mm vias to bottom caps: "one and only one via per each power pad".
  - DDR first and shortest, inner pads first; data outward, address inward; one topology per group; fan out every pad.
  - Quotes 20H and aspect ratio ≤10.
  - Read the vendor guide first (NXP DDR3 order: address, differential, control, data); route "piece by piece" from both ends.
  - The tips list attributed to him ("smaller cap closer", 10 µF+100 nF, connectors on one edge) is third-party.
- **Phil's Lab:** rough then section-by-section, with decoupling and crystal as separate steps; 2-layer: parts on one side, solid ground on the other, few plane-cutting vias; no splits under traces; clustered power vias.
- **Pease:** CAD ignored "thermals … crosstalk … good grounds"; fast layouts put hot transistors beside critical ones and buses over analog; criticality is "wrapped up in the heads of experts".
- **Williams:** planes minimise inductance (10 nH = 6 Ω at 100 MHz); fast parts mounted low; single-point critical comparator grounds; short traces; probe ground ≤1 in, coaxial probe points.
- **Hubing:** boards following long EMC guideline lists are worse than unguided ones. Common errors: blind guideline use; uncontrolled transition times; not following currents; not identifying critical traces; multiple grounds; poor decoupling; bypassed filters.

### Implications for our system
- **Template-first, then global placement** with cost = ratsnest + crossings + severity-weighted violations (S1 ≫ S2 ≫ S3).
- **Route and freeze critical nets first.**
- **The LLM's core job is the criticality map** (Pease). Scope and rationale on every rule guards against blind guideline-following (Hubing).
- **Feranec's rules feed the fan-out generator.** 20H is not a default.

---

## 10. Datasheet language → constraints

**Five statement types (RPA §8):**
1. Qualitative proximity ("as close as possible to LDOIN and PGND").
2. Relative priority (Rohm: inductor less close than CIN).
3. Pin/point connectivity (VOS at the COUT pad; shunt C via the VSS pin closest to ANT).
4. Explicit numbers.
5. Ordered procedures (SLYT614; BQ25895 "essential"), plus reference figures and designs (Nordic QFN vs WLCSP).

**Translation table** (defaults are heuristics to calibrate):

| Phrase | Constraint | Default |
|---|---|---|
| "as close as possible" (power cap) | proximity + same_layer + max_vias 0 + rank 1 + loop_area metric | 0.5 mm (0402/0603), 1.0 mm (0805+); MPS primary ≤2 mm |
| "close to IC" | lower-priority proximity | 3–5 mm |
| "connect X to Y at Z" | connect_at + separate_from(power path) | leave from the Z pad |
| "short and wide" | max_length + min_width | ≤5 mm; IPC width |
| "keep away from" | keepout(all layers) | 1–2 mm; no courtyard overlap |
| "do not route under" | rule area disallowing tracks/vias | — |
| "via near pad" / "fence" | via_near / via_fence | 0.5 mm; λ/20 |
| "mandatory/must" | hard (S1) | "should" → S2–S3 |
| numeric | DRC as written | store units, layer, condition |
| figure | relative_placement_template (vision, normalised to pin 1) | placement seed |
| ordered steps | placement_priority | — |

**Refinements (VR, IRP):**
- **Comparative constraints** (rank orders, distance ratios such as "IC much further from the TVS than the TVS from the connector") are more faithful than invented mm and still checkable.
- **Rule fields:** `source_scope`, `statement_strength`, `contested_by`, `applies_if`.
- **IRP contract:**
  1. match pattern;
  2. typed parameters with units and formulas;
  3. provenance and precedence 10 fab < 20 interface < 30 vendor family < 40 device datasheet, with `by_vendor` and recorded conflicts;
  4. backend K (DRU) / G (geometric) / S (simulation) / M (BOM);
  5. placement intents (anchor, adjacent, order_along_path, distance_window, same_side, keepout_ring, orientation, max_loop_area), separate from routing.
- **Resolution policy:**
  1. Highest precedence wins.
  2. Within a level, `by_vendor[profile]`.
  3. Otherwise the declared resolution, default "stricter" with an info finding citing both sources.
  4. [S] never beats [P] at equal precedence.
  5. [D] stays a warning until calibrated.
- **Vendor profiles are mandatory** (values differ 5–25×). For unknown vendors, use the tightest primary value with an info note.
- **Buck pack (IRP §11):** the §1 numbers as typed parameters. cin ≤2 mm is a hard window; the loop uses 2/10/20 mm² tiers; FB ≤3 mm is [D]. It adds a priority order, a same-side rule, an F.Cu inductor keep-out, SW = pad + minimum link with 0 vias, and FB with 0 vias on another layer behind a GND shield. A datasheet reference layout at precedence 40 sets the target loop area measured from the eval board.
- **Crystal pack:** the §4.4 annulus and pF budgets, plus a 3 mm HS keep-out [D] on F.Cu/In1.Cu, a magnetics keep-out, XIN/XOUT ≥3W [D], 0 test points, and an `insideArea('XTAL_KEEPOUT')` disallow rule (verify syntax).
- **KiCad 10:** `fromTo()` and ps units make many rules native. Loop area, plane-edge offsets, topology order and return-via distance stay geometric.

### Implications for our system
- **Datasheet Layout Guidelines and Layout Example sections are the primary input,** parsed into typed constraints with strength and scope; figures become templates.
- **No published taxonomy of datasheet layout language exists;** building one with a test corpus is novel work.

---

## 11. Hard vs soft vs explicit-selection (VR §3)

| Class | Rules | Encoding |
|---|---|---|
| **Hard DRC** | Fab absolute limits (DFM-01); courtyards (DFM-02); IPC-2221B floor raised by the safety standard (DFM-10); JLC silk 1.0/0.15 (DFM-11) | Board setup + `.kicad_dru` |
| **Hard topology** | No split/void crossing; single bridge; PWR-01 topology (CIN on IC layer, 0 hot-loop vias); PWR-06 FB from the COUT pad; PWR-07 single tie where "mandatory"; RF-03 named-pin shunt ground; RF-05 PCB keep-out polygon; RF-07 no digital under RF; AMS-02; (cross-domain: connector→TVS→IC with no stub/via; 0 test points on SerDes) | G-checker; reject |
| **Hard in scope** | Vendor numbers tied to a family, interface or data rate | Activate by `source_scope` |
| **Soft strong** | PWR-02 ≤0.13 mm next-layer GND; PWR-10 1 via/A; PWR-12 boot ratios (schematic); PDN-06 ≤20% bead current; PWR-15 EP vias | High-weight cost + warnings quoting the source |
| **Soft weak** | CIN ≤0.5–1 mm (MPS primary 2 mm); crystal ≤5 mm; FB ≤2–3 mm; RF↔SMPS 20 mm; λ/20 and 3–5 mm stitching; 2W/3W/5W (use h and computed crosstalk); 2 cm²/W; thermal spacing; MLCC 3–5 mm from V-score | Rank objectives, never DRC errors |
| **Context switch** | Copper under L (Rohm/TI); PWR-08 (Rohm vs MPS/TI); via tenting; "smallest closest" (MT-101 vs Bogatin/Archambeault); perimeter stitching (Ott vs Hubing); PMIC cuts (DA9080); 20-H (Montrose "fact, not fiction" for high-density multilayer vs Shim/Hubing slightly worse, LearnEMC "debunked"); crystal can/VSSOSC; copper under crystal | Both variants + a selector (power, layers, fab process, datasheet mandate); ask; log |
| **Scoped myth exceptions** | 90° harmless below multi-GHz, but ≤45° or curves on ESD paths (arcing below ~2.6 mm radius at 8 kV, SLVA680A) and arcs/135° on RF | Corner rule only on `ESD_UNPROTECTED` and `RF50` |

**Recalibrations:** drop PWR-08; split RF-05; keep AMS-02 at S1 with a limited escape; datasheet "mandatory" maps to hard.

**Why vendors disagree:** they optimise different objectives (Rohm: conducted HF noise and inductor Q; TI/MPS: loop area and shielding). Select by objective, not by vote.

### Implications for our system
- **Every rule carries its class.** Hard rules gate the output, soft rules weight the cost, and conflicts are shown to the user rather than resolved silently.

---

## 12. Checkers and role detectors (RPA §20, IRP §11)

### 12.1 Role detectors
- **Converter:** SW/LX/PH pins + VIN/PVIN + PGND/EP, or two FETs + L on a shared node. Confirm with datasheet keywords.
- **Topology:** L SW→VOUT with FB divider = buck; VIN→SW with rectifier to output = boost; SW→GND with negative output = inverting; coupled windings with primary FET = flyback/forward; two SW nodes with one L = 4-switch.
- **Converter roles:** CIN_HF (smallest package on VIN/PGND), BULK, COUT, FB_TOP/BOT, C_BOOT (BOOT/BST/CB↔SW), SNUB (series RC SW→GND), RSENSE (≤100 mΩ to CS±/SENSE), AGND/PGND by name. Hot loops from §1.2.
- **Flyback:** transformer primary on the HV bulk + drain; windings classified primary/secondary/bias; clamp, Y-cap (cross-class pins), spark gaps, L_post.
- **H-bridge:** FET pairs on an SH node to a connector; GHx/SHx/GLx/SLx/SPx/SNx/VDRAIN/VCP pins; per-phase bypass, shunt, CSA caps, bulk.
- **Charger:** PMID/VBUS/SW/BAT/REGN/BTST/ILIM/TS → ordered priority + CHG-02.
- **BMS:** VC0…n, SRP/SRN, BAT, PACK, CHG/DSG; cell RCs, Kelvin shunt, FET pours; voltage classes by cell index.
- **LED:** CSP/CSN → sense pair + filter at the IC; SW keep-out under the IC.
- **Thermocouple:** TC connector/nets + NTC/RTD/sensor IC. **Bridge:** 4/6-wire excitation/sense nets. **TIA:** op-amp with R_F ≥~100 kΩ + photodiode on IN−. **Class-D:** OUT±/SW/BST/PVDD/VBST/Vsense.
- **Crystal:** OSC_IN/XTAL1/XIN/XTAL_P + OSC_OUT + crystal + caps (+ series R). **RF** chain; **ADC** AGND/DGND.

### 12.2 Constraint schema (RPA §20B)
YAML objects:
- loop_area (ordered members, max_mm2, same_layer, max_vias);
- proximity with `require_net_match` (inductor dot pad = SW);
- connect_at with `forbid_shared_copper_with`;
- keepout (victim class, aggressors, clearance, all layers);
- solid_reference (hot-loop hull + 1 mm on In1.Cu = GND);
- via_array (drill, pitch, fill).

Each carries `severity` and `source`.

### 12.3 Deterministic checks (pcbnew Python / IPC API)
- **Loop-inductance estimator (first-class).** Shoelace area of ordered pads plus a routed-path variant with a via penalty; L ≈ µ0·h·len/w over a plane. Inputs: pad gap, trace W/L, via count and length, plane depth. Calibrate on Axotron, Archambeault, AN-139, SNVA803 and EPC; judge against SLAA896 pH budgets.
- **Proximity:** pad-edge distances; same side; via count on the shortest copper path (graph search).
- **Reference integrity:** rasterise adjacent-layer zones under regions or along tracks; flag voids, slots, foreign nets, split crossings.
- **Coupling:** layer-aware (same and ±1) parallel-run length and minimum gap.
- **Keep-outs:** all-layer copper vs antenna, module and inductor polygons.
- **Fences and stitching:** maximum GND-via gap along the RF centreline; pour maximum gap.
- **Thermal:** EP via count and pitch; P vs connected copper; hot↔sensitive distances; airflow cone; cut-vs-radial angle.
- **DFM:** courtyards; tombstone symmetry; rotation histogram; fiducials; test-point coverage; class edge/V-score distances; HV clearance.
- **PDN:** cap and via distance per pin; derated C vs Z_t; bead resonance; full RLC sweep.
- **Specials:** the checks named in the body's rule IDs (PWR-17, FLY-02/05, CHG-02, HC-01, BMS-03, AUD-05, AMS-07, SEN-01/04/05, XTAL-PAR), plus an SW-area cap.
- **Safety engine:** lookup → surface-geodesic creepage + 3-D clearance.
- **KiCad encoding:**
  - Net classes `PWR_HOT`, `SW`, `SENSITIVE` (FB/COMP/RT/SS/REF/crystal), `RF50`, `HV`, `ANALOG`, `DIGITAL`, with widths and clearances from IPC and fab limits.
  - `.kicad_dru` rules with `A.NetClass`, `insideArea()` and layer conditions (e.g. SENSITIVE↔SW ≥1 mm); rule areas from keep-outs; class-based courtyard and edge rules.
  - Everything else emits **KiCad-style marker reports** for the LLM repair loop.
  - Verify syntax on the installed KiCad.

### 12.4 Criticality map (Pease)
Before any geometry, the LLM lists, each with severity and provenance:
- hot loops;
- high-Z and summing nodes;
- matched pairs;
- thermal aggressors and victims;
- noisy buses and their neighbours;
- isolation barriers.

A human corrects the map, and the checks consume it.

### Implications for our system
- **Division of labour:** LLM = extraction, classification, templating; code = geometry and physics; human = safety classes and criticality review.
- **No published system extracts hot loops from netlists,** and no open-source KiCad plugin implements these backends. Validate on open-source KiCad boards with known regulators; calibrate on TI, ADI and Espressif eval layouts.

---

## 13. Idea inventory
Tags: RPA, VR, IRP (§ = section).

1. Hot loop first, smallest, one layer, plane under it (RPA§1)
2. Topology table of hot vs continuous branches (RPA§1)
3. INTVCC/driver loop as second hot loop (RPA§1, VR)
4. Overshoot V = L·di/dt calculator (VR, IRP§8)
5. Loop-L anchors: AN-139, SNVA803, EPC (RPA§1, IRP§8)
6. Loop-area tiers 2/10/20 mm² [D] (IRP§8)
7. Warn if overshoot >0.2×V_DS,max (IRP§11)
8. Efficiency-impact estimate from loop L (IRP§8)
9. Prefer vertical loops; thinner boards cancel better (RPA§1, VR)
10. ≥4 layers, ≤0.127 mm L1–L2 under power stages (VR, IRP)
11. Isolated return for ≥100 W supplies (VR)
12. SLYT614 order as placement_priority (RPA§1)
13. CIN routed immediately; no hot-loop vias (RPA§1, VR)
14. MPS <2 mm CIN default window (IRP§8)
15. WCSP: SW under CIN; vias in SW→L instead (VR)
16. System vias outside the CIN–IC path (VR)
17. Converter parts on one side (VR)
18. EN/PG placed last (VR)
19. No far-side CBYPASS or freewheel diode through vias (VR)
20. Bulk CIN up to ~20 mm from HF cap (IRP§8)
21. Via counts at power pins; >20 between input caps (IRP§8)
22. Rohm via-inductance formula (IRP§8)
23. SW-area cap relative to pads (RPA§1)
24. SW width ≤2.54 mm (IRP§8)
25. SW on one layer only (RPA§13)
26. Cool via PGND/EP, not SW copper (RPA§1, §5)
27. Bootstrap-R edge slowing as EMI knob (RPA§1)
28. Inductor dot on SW; pin-1 = dot convention (RPA§1)
29. Copper under L as a context switch (VR)
30. Sensitive keep-out under L/near SW, all layers (RPA§1)
31. FB Kelvin from COUT pad (RPA§1, VR)
32. FB divider at pin, no vias (IRP§8)
33. FB shielded layer if R_FB >100 kΩ (IRP§8)
34. FB angular-sector test (RPA§1)
35. AGND island, net-tie count = 1 (RPA§1)
36. Surface TI FB-ground tension for selection (VR)
37. Plane + local loop + tie over literal star (RPA§1)
38. PMIC ground cuts only when mandated (VR)
39. Gate loop paired, Kelvin source (RPA§1)
40. EPC L_G ≤ ¼(R_G+R_S)²C_GS check (VR)
41. Boot ratios ≥10× schematic check (VR)
42. Smallest driver bypass nearest (VR)
43. Snubber at IC SW/GND pins; loop check (RPA§1, VR)
44. RCD values + series damping R (VR)
45. Kelvin tap at inner-pad centre; equal pair (VR)
46. Copper TCR awareness for 2-terminal shunts (VR)
47. Sense pair behind a shield plane (VR)
48. DCR sense: R at L, C at IC (RPA§1)
49. LDO output through COUT first (RPA§1)
50. Converter role detector (RPA§20)
51. Topology classifier from L connectivity (RPA§20)
52. Role-assignment rules (CIN_HF…RSENSE) (RPA§20)
53. Typed YAML constraint schema (RPA§20)
54. Datasheet constraints override generic defaults (RPA§20)
55. Rank decoupling by mounting L (RPA§2)
56. Alternate cap orientation in clusters (RPA§2)
57. Spread caps (RPA§2)
58. Max C per package (RPA§2)
59. Via-in-pad vs cost/thieving trade-off (RPA§2)
60. Archambeault depth table in estimator (VR)
61. Plane pairs high, thin, no necks (RPA§17)
62. Via-at-pad plane connections (VR)
63. Z_t with transient share only (RPA§17)
64. Flat profile; peak ≤1.57× / 3×Z_t (RPA§17)
65. Q per peak; rogue-wave warning (RPA§17)
66. ESR damping, C = L/R² bulk (RPA§17)
67. Open-source lumped-RLC PDN screener (RPA§17)
68. Cavity-mode vs harmonics check (RPA§17)
69. MLCC bias derating (RPA§2)
70. Beads only on need, ≤20% rated (RPA§2)
71. Bead resonance vs f_sw; damping A/B/C (RPA§2, VR)
72. IPC width + IR drop per power net (RPA§2)
73. Rohm 1/0.7 mm/A widths (VR, IRP)
74. Conservative via ampacity, conflict logged (RPA§11, §14)
75. Return vias; ≤1 µF split stitching caps (RPA§2, VR)
76. Pre-layout BOM checks (RPA§2, VR)
77. RF50 class, solver geometry (RPA§3)
78. RF branch/stub detector (RPA§3)
79. Match at pin; named-pin shunt ground (RPA§3, VR)
80. Inner keep-out under matching (VR)
81. Fence/stitching max-gap checker (RPA§3)
82. λ/20 worked table (RPA§3)
83. Antenna keep-out from module figure, all layers (RPA§3, VR)
84. Enclosure clearance to mechanical checklist (VR)
85. Ground-plane size window, embedded antennas (VR)
86. Stitched edge ring, power pulled back (VR)
87. RF length before bus length (VR)
88. Reference plane for all traces incl. DC (VR)
89. Power through bypass/bulk before module pin (VR)
90. Mask under GNSS receivers, no open vias (VR)
91. Per-part RF data store (VR)
92. Reference-design deference (RPA§8)
93. RF↔SMPS as ranked objective; cans/fences (RPA§3)
94. Shield-can footprint rules (RPA§3)
95. Scoped corner rules (RF, ESD) (RPA§3, VR)
96. Acute-angle check, all nets (RPA§3)
97. One partitioned plane; ADC straddles (RPA§4)
98. Ground strategy from ADC bits (RPA§15)
99. Ott jumper validation test (RPA§4)
100. Split-crossing detector; one bridge (RPA§4)
101. AGND/DGND tie at package (RPA§4)
102. 300 mV plane limit; Schottky clamps (VR)
103. ADC output buffer with series R (VR)
104. Guard-ring net check, both sides (RPA§4)
105. Summing-node copper minimisation (RPA§4)
106. Matched-pair mirror metric (RPA§4)
107. Common-centroid symmetry (RPA§19)
108. Kelvin on all precision sense points (RPA§4)
109. TC CJ co-location, symmetric routing (RPA§15)
110. Bridge ratiometric, 6-wire, balanced, R_G at pins (RPA§15)
111. TIA regime classifier (RPA§15)
112. Low-leakage part-type check (RPA§15)
113. Ground-noise budget from LSB table (RPA§15)
114. Crystal distance annulus (IRP§7)
115. Crystal trace-C budget (IRP§7)
116. Crystal guard pour rule area (IRP§7)
117. Zero test points on osc nets (IRP§7, VR)
118. XIN cap first; series R at chip; magnetics keep-out (IRP§7)
119. Crystal vendor switches (IRP§7)
120. C-shaped via ring at clock/RF transitions (IRP§7, §9)
121. Safety-spacing lookup engine (RPA§9)
122. Surface-geodesic creepage checker (RPA§9)
123. 3-D clearance checker (RPA§9)
124. LLM net-class/grade proposal, human-confirmed (RPA§9)
125. All-layer barrier keep-out (RPA§9)
126. Slot-width validity per PD (RPA§9)
127. Groove-credit formula (RPA§9)
128. Group-I-on-group-III trap detector (RPA§9)
129. Hi-pot only for functional isolation (RPA§9)
130. Spark gaps, Y-cap routing, fuse-first checks (RPA§9)
131. Stricter of IPC-2221B and safety std (VR)
132. Flyback loop identification (RPA§10)
133. Nested-loop containment test (RPA§10)
134. Transformer belly/drain keep-out (RPA§10)
135. FB before post-filter L (RPA§10)
136. One star join per side (RPA§10)
137. π-filter L in negative leg (RPA§10)
138. Half-bridge commutation-loop check (RPA§11)
139. Gate ≥20 mil, paired with SW (RPA§11)
140. Net ties enforce Kelvin (RPA§11)
141. 2-layer ground grid/mesh (RPA§11)
142. Teardrops (RPA§11)
143. In-path passives side by side (RPA§11)
144. Bulk at entry, ceramics at bridge (RPA§11)
145. Provenance flags vendor-doc errors (RPA§11)
146. LED sense pair; no SW current under IC (RPA§12)
147. LED heat away from sense parts (RPA§12)
148. Charger ordered priority (RPA§13)
149. BMS filter at IC, not shunt (RPA§13)
150. Ordered cell traces; spread balance resistors (RPA§13)
151. Monitor ground off high-current copper (RPA§13)
152. Spacing class from cell index × V (RPA§13)
153. Narrowest cross-section check (RPA§14)
154. Vias where current enters/leaves pads (RPA§14)
155. Heavy copper vs fine pitch check (RPA§14)
156. Overlapped supply/return (RPA§14)
157. Busbar keep-outs; transitions hot spots (RPA§14)
158. Copper weight by dissipation (RPA§14, §18)
159. Per-pin pH loop budgets (RPA§16)
160. No adjacent-layer coupling for switch outputs (RPA§16)
161. Output filter at IC; connector at cap pads (RPA§16)
162. Quiet-side inputs with floods (RPA§16)
163. <100 kHz return-path planning (RPA§16)
164. Thermal screening estimator (RPA§18)
165. Correct Ψ_JB/Ψ_JT use (RPA§18)
166. 15.3 cm²/W and area formula (RPA§18)
167. EP vias 1 mm pitch, direct connect (RPA§18)
168. Cut-orientation check (RPA§18)
169. Bottom heatsink preference (RPA§18)
170. Via tenting as assembly-process switch (VR)
171. Paste 50–70%; void-limit selection (RPA§5, VR)
172. Spread hot parts; avoid corners (RPA§5)
173. Sensitive parts upstream; airflow cone (RPA§5)
174. Arrhenius life in distance scoring (RPA§5)
175. Fab packs set min only (IRP§10)
176. DRC absolute, router recommended (RPA§6)
177. Multi-fab profile table (IRP§10)
178. Courtyard B 0.25 mm default (RPA§6)
179. Tombstone asymmetry metric (RPA§6)
180. Rotation histogram (RPA§6)
181. Single-sided SMT preference (RPA§6)
182. Fiducial checks, corrected rules (RPA§6, VR)
183. Test-point coverage, corrected clearances (RPA§6, VR)
184. Class-based edge/V-score distances (RPA§6)
185. Panel/tab geometry (RPA§6, IRP§10)
186. Derived mounting-hole keep-out (IRP§10)
187. 3-D height zones (RPA§6)
188. Silk check, corrected minimums (VR)
189. Expert placement order (RPA§7)
190. Pre-routing placement score (RPA§7)
191. Template-first, then global placement (RPA§20)
192. Region partition with boundary parts (RPA§20)
193. Route critical first, freeze, re-check (RPA§20)
194. BGA central; fan-out by pitch (RPA§7)
195. Fan-out generator: 1 via/pad; DDR inner first (RPA§19)
196. Termination at driver; ESD at connector (RPA§19)
197. Rough-then-refine sectioned placement (RPA§19)
198. Datasheet statement taxonomy (RPA§8)
199. Phrase→constraint table (RPA§8)
200. Statement strength → severity (RPA§8)
201. Vision extraction of layout figures (RPA§8)
202. Comparative constraints instead of mm (VR)
203. applies_if/source_scope/strength/contested_by fields (VR)
204. Authority-ranked provenance per constraint (RPA§20)
205. Rule-pack schema (IRP§11)
206. Precedence ladder + "stricter" resolution (IRP§11)
207. Mandatory vendor profiles (IRP§11)
208. Eval-board layout overrides loop target (IRP§11)
209. Hard/soft/switch/scope classification (VR)
210. Severity recalibrations (VR)
211. Context-dependence flags (RPA§20)
212. Low-authority numbers soft only (RPA§20)
213. Python checks emitting KiCad markers (RPA§20)
214. Role net classes + .kicad_dru generation (RPA§20)
215. Reviewable criticality map (RPA§19, §20)
216. LLM extracts; code checks (RPA§20)
217. Thermal + PDN screening in loop (RPA§20)
218. Validation corpus of KiCad boards (RPA§20)
219. Calibrate on vendor eval layouts (RPA§20, IRP§11)
220. Anti-rule list against folklore (VR)
221. Scope + rationale against blind rule-following (VR)
222. 20-H, perimeter stitching, guards non-default (VR)
223. Separate board/shield box for >35 dB isolation (RPA§19)
224. Fast parts mounted low; coax probe points (RPA§19)
225. Surface copper-weight decision early (RPA§14)
226. Capacitor-combination ringing awareness (RPA§19, VR)
