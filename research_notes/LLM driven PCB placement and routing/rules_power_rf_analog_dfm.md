# PCB Placement and Routing Rules: Power Conversion, PDN and Decoupling, RF, Analog and Mixed-Signal, Thermal, DFM/DFA, and Placement Method

How this was researched, and its limits: WebFetch could not resolve DNS in this session, and the egress proxy returned HTTP 403 for direct downloads from ti.com, analog.com and most vendor hosts. All findings below therefore come from extended web-search extracts of the cited documents, not from reading the full PDFs. Each claim carries the URL of the document the extract came from. Exact figures or wording from primary PDFs (TI SLYT614, ADI AN-136/AN-139, ST AN2867 and others) should be spot-checked before they are hard-coded as constraints. Where only a vendor blog backs a number, it is marked "(low authority)". Rules I derived from circuit physics rather than from a source are kept in the "Inferences" subsections.

Rule table format used throughout:
`ID | Rule | Numeric guideline | Why (physics) | Applies when | Severity | How to check automatically | Source`
Severity scale: **S1** = functional or safety failure likely; **S2** = EMI, thermal or performance failure likely; **S3** = yield or margin loss; **S4** = best practice.

---

## 1. Switching power converters (buck, boost, buck-boost, flyback, LDO): hot loops, input caps, switch node, feedback, inductor, grounding, snubbers, gate drive, current sense, thermal vias

### Takeaway
Every source puts one rule first: find the loop that carries fully switched (pulsating, high di/dt) current and make it physically as small as possible. In a buck that loop is CIN to the high-side switch to the low-side switch, in a boost it is the low-side switch to the rectifier to COUT, and in a flyback it is both the primary loop and the secondary loop. Place it first, on one layer, with a solid ground plane directly under it. Everything else ranks below it, in this order: small switch-node copper, inductor next to SW, COUT, then feedback taken by Kelvin connection at COUT and routed away from SW and the inductor, then one quiet AGND tie.

### Cited Findings

**Hot loop identification and priority**
- AN-139 (Kueck, Linear/ADI) calls the loop that carries the fully switched AC current the dominant EMI source and names it the "hot loop". The on-cycle and off-cycle loops are not the ones to optimize. CIN should source all relevant AC currents, and those currents end at COUT. — [ADI AN-139](https://www.analog.com/en/resources/app-notes/an-139.html); [AN-139 PDF mirror](https://theengineer.markallengroup.com/production/content/uploads/2015/01/an139f.pdf)
- AN-139 also says a copper plane under the hot loop improves both functional and EMI behaviour. Kueck's Part 2 article recommends a board of four or more layers. Its reasoning is that a close inner-layer shield cancels the hot-loop field far better than a shield more than 1 mm away, which is what a 2-layer board gives. — [Kueck Part 1](https://www.analog.com/media/en/technical-documentation/technical-articles/kueck_layout_power_supply_part_1.pdf); [Kueck Part 2](https://www.analog.com/media/en/technical-documentation/technical-articles/Kueck_Layout_power_supply_part_2.pdf)
- AN-136 says to keep the supply output near the load. It also says to put a ground or DC plane layer between the power-stage layer and the small-signal layer. The pulsating loop should be as small as possible, built from short, wide traces, and decoupled with a low-ESL/ESR X5R/X7R ceramic. — [ADI AN-136](https://www.analog.com/en/resources/app-notes/an-136.html); [PDF4PRO copy](https://pdf4pro.com/view/an136-pcb-layout-considerations-for-non-37e884.html)
- In an AN-136 multiphase example, adding a 1 µF high-frequency input cap per channel shrank the hot loop and kept switching waveforms stable up to 30 A (secondary summary). — [PWChip summary of AN-136](https://www.pwchip.com/en/article/61.mhtml)
- TI SLYT614 ("Five steps to a great PCB layout for a step-down converter", 1Q 2015, TPS62130A example) gives this order. Step 1: the input capacitor is the most important part, so place it first after the IC and route it immediately, before anything else can block its path. Step 2: the inductor, with minimum SW-node copper area, plus an RC snubber if one is used. Step 3: output capacitors and the VOS pin. Step 4: small-signal components; VOS is the most critical small-signal connection. Step 5: a single-point ground connection to the rest of the system. — [TI SLYT614](https://www.ti.com/lit/an/slyt614/slyt614.pdf); [TI SLYT614 (Chinese edition)](https://www.ti.com.cn/cn/lit/an/zhct286/zhct286.pdf?ts=1792028952371)
- SLYT614 shows an RC snubber layout but gives no R or C values; a TI E2E thread notes the omission. — [TI E2E TPS62130A snubber thread](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/927858/tps62130a-snubber)
- TI SLVA818: place CIN as close as possible to the IC, with wide, short traces to VIN and PGND. Minimize the area of the CIN → VIN → PGND → CIN loop. — [TI SLVA818](https://www.ti.com/lit/pdf/slva818)
- TPS62130 datasheet: connect VOS in the shortest way to VOUT at the output capacitor. A direct common connection of AGND and PGND to the exposed thermal pad and to the system ground plane is "mandatory". It recommends a 22 µF X7R/X5R output capacitor. — [TI TPS62130 datasheet](https://www.ti.com/lit/ds/symlink/tps62130.pdf)
- Rohm's buck layout note says to put the input capacitor and freewheel diode on the same surface layer as the IC terminals, as close to the IC as possible. The inductor should be close to the IC but "no need to be as close as input capacitor". Do not expand switch-node copper more than needed, because it radiates. — [Rohm "PCB Layout Techniques of Buck Converter"](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf); [Rohm TechWeb overview](https://techweb.rohm.com/product/power-ic/dcdc/2734/)
- Boost (TI SLVA773, "Five Steps to a Good PCB Layout of the Boost Converter"): place the output capacitor close to the IC with short, wide traces. If vias are needed, use about one via per ampere. A small-package capacitor can sit next to the IC while bulk caps go farther away. — [TI SLVA773](https://www.ti.com/lit/an/slva773/slva773.pdf)
- Boost (TI SNVA731): the loop formed by the output capacitor, the diode and the regulator ground is the most critical PCB feature. Make it short and wide with minimum area. — [TI SNVA731](https://www.ti.com/lit/an/snva731/snva731.pdf)
- A target of "under 1 cm² if possible" for the boost hot loop appears only in a vendor calculator page (low authority). — [Firgelli boost calculator](https://www.firgelliauto.com/blogs/engineering-calculators/boost-converter-calculator)

**Vertical vs lateral hot loop (multilayer)**
- EPC calls the "internal vertical" layout optimal: bus capacitors sit next to the FETs and the power loop closes vertically, using the first inner layer as the return. In a lateral loop, inductance depends strongly on how far the shield plane is from the loop, so the shield should be as close as possible; current in the shield cancels flux but adds eddy loss. In a vertical loop, opposing currents on top and bottom layers self-cancel, and that cancellation improves as the board gets thinner. — [EPC layout presentation](https://epc-co.com/epc/Portals/0/epc/documents/presentations/High-Performance%20Layout%20Techniques%20to%20Maximize%20GaN%20Device%20Performance.pdf); [EPC WP010](https://epc-co.com/epc/Portals/0/epc/documents/papers/Optimizing%20PCB%20Layout%20with%20eGaN%20FETs.pdf)
- A DTU paper on GaN PCB layout prefers the vertical loop in multilayer designs for its lower inductance, but notes it is harder to characterize because of via effects and inductive coupling. — [DTU IAS 2020 paper](https://orbit.dtu.dk/files/236953218/IAS_accepted_PCB_for_GaN_2020.pdf)

**Switch-node copper**
- Keep SW copper small, because its high dV/dt couples capacitively into nearby traces, planes and heatsinks. A TI automotive AAJ article recommends a short, wide SW pour and a full ground plane under the SW node on multilayer boards. — [TI SLYT682](https://www.ti.com/lit/slyt682); [HS Electronik buck guide](https://hs-electronik.com/news/buck-converter-pcb-layout-hot-loops-feedback-guide)
- There is a real conflict between cooling and EMI. A hot device wants a large drain pad, but that pad is a high-dV/dt antenna. — [USPTO 10763221](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10763221)
- Resolve the conflict with thermal vias to other layers, not by enlarging SW copper. — [Rohm buck layout note](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf); [HS Electronik](https://hs-electronik.com/news/buck-converter-pcb-layout-hot-loops-feedback-guide)
- Slowing edges (for example, a series resistor in the bootstrap path) lowers dV/dt and EMI at the cost of efficiency. — [Richtek AN045](https://www.richtek.com/Design%20Support/Technical%20Document/AN045)
- Sources conflict on copper under the inductor. TI suggests a top-layer copper keep-out under the inductor with a ground plane below. HS Electronik says not to put copper under the inductor unless the converter's guidance supports it. — [TI SLYT682](https://www.ti.com/lit/slyt682); [HS Electronik](https://hs-electronik.com/news/buck-converter-pcb-layout-hot-loops-feedback-guide)

**Inductor orientation and placement**
- Würth ANP047 measured emissions up to 8 dB lower with the dotted (start-of-winding) end connected to the switch node. The mechanism: the dot is the inner winding, so the outer winding sits at quiet VOUT and acts as an electrostatic shield. H-field emissions do not change with orientation, so this is an E-field effect. — [Würth ANP047c](https://www.we-online.com/components/media/o109027v410%20ANP047c_The%20Behavior%20of%20Electro-Magnetic%20Radiation%20of%20Power%20Inductors%20in%20Power%20Management.pdf); [ANP047b mirror](https://www.mouser.com/pdfDocs/ANP047b_ENG_The_Behavior_of_Electro-Magnetic_Radiation_of_PI_in_Power_Management.pdf)
- Shielding material suppresses magnetic fields only, so orientation still matters for shielded inductors. Do not route signals under power inductors. — [NextPCB shielded vs unshielded](https://www.nextpcb.com/blog/shielded-vs-unshielded-inductors-emi-pcb-placement)
- Dissent: a DigiKey forum thread argues orientation "does not matter". It is not a measurement study. — [DigiKey forum](https://forum.digikey.com/t/inductor-behavior-why-orientation-does-not-matter/17072)

**Feedback, Kelvin sense, AGND/PGND**
- The feedback node is high-impedance. Never route it under the inductor or next to SW on any layer. Take the sense point at the output capacitor, not at the inductor. — [HS Electronik](https://hs-electronik.com/news/buck-converter-pcb-layout-hot-loops-feedback-guide); [All About Circuits buck layout](https://www.allaboutcircuits.com/technical-articles/techniques-dc-dc-buck-converter-PCB-layout/); [EEVblog thread](https://www.eevblog.com/forum/projects/buck-converter-feedback-from-power-plane/)
- Put a small AGND pour around the feedback components. Do not share the AGND trace with the high-current PGND return. — [SchematicsHub buck layout](https://schematicshub.com/articles/buck-layout)
- AN-136: give the top-FET gate-drive trace and the switch-node trace a minimal shared loop area. Run the bottom-FET gate trace next to a PGND trace. Keep current-sense traces away from switching nodes. — [EDN reprint of AN-136](https://edn.com/Home/PrintView?contentItemId=4390811)

**Gate drivers and bootstrap**
- Use wide, short driver-to-gate traces. Treat the Kelvin source return as top priority for low common-source inductance, and place the driver close to the FET. — [EPC WP008](https://epc-co.com/epc/Portals/0/epc/documents/papers/eGaN%20FET%20Drivers%20and%20Layout%20Considerations.pdf); [EPC layout presentation](https://epc-co.com/epc/Portals/0/epc/documents/presentations/High-Performance%20Layout%20Techniques%20to%20Maximize%20GaN%20Device%20Performance.pdf)
- TI: keep the driver output loop minimal and the driver-ground-to-source path as short as possible. — [TI SLYP754](https://www.ti.com/lit/ml/slyp754/slyp754.pdf)
- Place bootstrap and VDD bypass caps as close as possible to the driver supply pins, with the smallest cap nearest the pins. Rule of thumb: C_boot ≈ 10× the gate capacitance, and C_VDD ≈ 10× C_boot. — [TI SLUA887](https://www.ti.com/lit/SLUA887); [TI SLUAAM3](https://www.ti.com/lit/pdf/sluaam3)

**Flyback and snubbers**
- Minimize the loop area of the fast dI/dt paths. — [TI "Under the Hood of Flyback SMPS Designs"](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/188/5635.Under-the-Hood-of-Flyback-SMPS-Designs.pdf)
- The RCD clamp is the most common and cost-effective drain-ringing clamp: a high-voltage diode, a high-voltage capacitor in the nF range, and a resistor in the hundreds of kΩ. — [Infineon AN-1195](https://www.infineon.com/dgdl/an-1195.pdf?fileId=5546d462533600a40153559b13df115a)
- Secondary rectifier ringing can be more destructive than the primary waveforms, and Schottky rectifiers are especially sensitive to it, so a secondary snubber is sometimes needed. — [ADI Flyback Snubber Design](https://ez.analog.com/cfs-file/__key/telligent-evolution-components-attachments/00-330-01-00-00-06-34-74/FlybackSnubberDesign.pdf)
- Place snubber R, C and D as close as possible to the switch node and transformer, using low-ESL SMD ceramics. Avoid shared primary/secondary return paths (tutorial, low authority). — [next.gr flyback snubber tutorial](https://www.next.gr/tutorials/switching-power-supplies/flyback-snubber-design-tutorial)

**Current-sense (Kelvin) connections**
- Keep sense traces equal in length, equal in width and as short as possible. Put the sense amplifier and the shunt on the same PCB side. Connect the sense traces at the points the shunt manufacturer recommends. — [onsemi DN05117](https://www.onsemi.com/download/design-notes/pdf/dn05117-d.pdf)
- Prefer a 4-terminal shunt (separate current and sense terminations). A 2-terminal part can use PCB-trace Kelvin connections but is less precise at high current. — [Bourns N1702](https://www.bourns.com/docs/technical-documents/technical-library/current-sense-pulse-power-high-power-resistors/application-notes/bourns_n1702_current_sense_accurate_measurement_appnote.pdf); [DigiKey current measurement part 1](https://www.digikey.com/en/articles/fundamentals-of-current-measurement-part-1-current-sense-resistors)
- Tap from the inner, symmetric centre of each pad. Route sense lines as a tightly coupled pair, and keep the amplifier as close to the shunt as possible (vendor guide). — [NextPCB current-sense guide](https://www.nextpcb.com/blog/current-sense-resistor-pcb-layout-kelvin-connection)

**LDO**
- Place the LDO input capacitor as close as possible to the LDOIN and PGND pins, because trace impedance contributes to dropout and load-regulation effects. — [Renesas DA9080 AN-PM-179](https://www.renesas.com/en/document/apn/da9080-pcb-layout-recommendations)
- Route the output through the output capacitors first, and only then change layers or run to remote loads. Recommendations from the same set of vendor notes: copper-plugged vias for the lowest via impedance and best thermal performance; output caps "within ~2 mm"; about 2 cm² of copper per 1 W to stay below 85 °C. The last two are low authority. — [Renesas AN-PM-179](https://www.renesas.com/en/document/apn/da9080-pcb-layout-recommendations); [MPS AN065](https://media.monolithicpower.com/document/PCB_Layout_Design_Guidelines_for_NB67xSeries.pdf); [PCBWay LDO blog](https://www.pcbway.com/blog/PCB_Design_Layout/LDO_Power_PCB_Layout_Design_Guidelines_From_Basics_to_Best_Practices_8f3387c6.html); [Aivon LDO blog](https://www.aivon.com/blog/pcb-design/pcb-design-essentials-for-ldo-power-supplies/)
- LDO dissipation is P = (VIN − VOUT) × IOUT, and the package plus PCB copper must carry it away. — [PCBWay LDO blog](https://www.pcbway.com/blog/PCB_Design_Layout/LDO_Power_PCB_Layout_Design_Guidelines_From_Basics_to_Best_Practices_8f3387c6.html)

**Thermal vias under exposed pads (power ICs)**
- TI SLOA122: via diameter 0.3 mm or less at 1 mm pitch. Vias may be plugged to prevent solder loss. — [TI SLOA122](https://www.ti.com/lit/pdf/sloa122)
- Renesas TB389: a grid at 1.0–1.2 mm pitch, 0.3–0.33 mm diameter, barrel plated to about 1 oz, connected to buried planes. More vias help, with diminishing returns. — [Renesas TB389](https://www.renesas.com/en/document/oth/tb389-pcb-land-pattern-design-and-surface-mount-guidelines-qfn-packages)
- Rohm: use small (~0.3 mm) vias that can fill with solder. Beware solder suction through open through-vias during reflow, and add vias around the IC. — [Rohm buck note](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf)

### Inferences

**Hot-loop membership by topology.** The hot loop is the set of branches whose current changes abruptly from 0 to I at each switching edge. Branches with continuous (triangular) current, such as the inductor and the cap on the inductor side, are not in it. Derived from circuit analysis and consistent with AN-139 and SNVA731:

| Topology | Hot loop members (place first, tightest) | Not hot (continuous current) | Notes |
|---|---|---|---|
| Buck (sync or async) | CIN_HF(+) → HS switch (or VIN pin) → SW → LS switch / catch diode (or PGND pin) → CIN_HF(−) | L, COUT | Integrated regulators: hot loop = CIN_HF + VIN/PVIN pin + PGND pin. CIN_HF is the smallest-package ceramic. |
| Boost | LS switch (SW→PGND) → rectifier / HS switch (SW→VOUT) → COUT_HF → PGND | L, CIN | COUT_HF ground must return to the IC PGND by the shortest path (SNVA731). |
| Inverting buck-boost | CIN, switch, diode / sync FET, COUT: all in one series loop | L | Both caps are in the hot loop, so place CIN and COUT grounds side by side at the IC. |
| 4-switch buck-boost | Two loops: input half-bridge with CIN, and output half-bridge with COUT | L | Each half-bridge gets its own HF cap right at its FETs. |
| SEPIC / Ćuk | Switch → coupling cap → rectifier → COUT → ground → switch | L1, L2, CIN | Inference only; confirm against the controller datasheet. |
| Flyback | (1) primary: CIN → primary winding → FET → Rsense → CIN; (2) clamp: primary → clamp diode → clamp RC → back; (3) secondary: secondary winding → rectifier → COUT | Output LC post-filter | Three separate hot loops. Respect primary/secondary creepage (see section 6). |
| Half-bridge gate drive | Driver OUT → gate → Kelvin source → driver return; bootstrap loop C_BOOT ↔ HB/HS pins | — | The gate loop must not share the power-source inductance (EPC). |
| LDO | No switching loop; CIN → VIN/GND for load transients, COUT for stability | — | Thermal dominates. |

**Power rule catalog (machine-actionable; numbers are defaults to tune per datasheet):**

| ID | Rule | Numeric guideline | Why (physics) | Applies | Sev | Auto-check | Source basis |
|---|---|---|---|---|---|---|---|
| PWR-01 | Place CIN_HF first, same layer as the IC, across the VIN and PGND pins | Pad-edge gap ≤ ~0.5–1 mm (heuristic); 0 vias in the loop | Loop inductance L ∝ area. V_spike = L·di/dt (example: 1 nH × 1 A/ns = 1 V of ringing) | All bucks, any IC with PVIN/PGND | S1 | Polygon of the hot-loop pad centroids → area; count vias on the CIN↔pin path; same-layer test | SLYT614, SLVA818, Rohm, AN-136 |
| PWR-02 | Solid GND plane on the layer directly beneath the hot loop, no slots | Inner plane ≤ ~0.1–0.2 mm below top (stackup); ≥4 layers preferred | Image current in the adjacent plane cancels flux, so inductance and radiation fall | Multilayer | S2 | Rasterize the hot-loop bounding box on L2; require 100% GND zone fill, no other nets | AN-139, Kueck, EPC |
| PWR-03 | Minimize SW copper: only enough for current plus a short link to L | Area ≤ the footprint of the SW pins plus the L pad plus the link | Large dV/dt plate = capacitive coupling and E-field antenna | All switchers | S2 | Sum of SW-net copper area; flag if > k × (SW pad area + L pad area) | Rohm, SLYT614, TI SLYT682 |
| PWR-04 | Inductor adjacent to the SW pin; dot (pin 1 / start of winding) on SW | Second priority after CIN | Outer winding at VOUT shields the inner high-dV/dt winding (up to 8 dB E-field) | Inductors with a polarity mark | S3 | Check the net of the inductor's start pin == SW (needs footprint pin-1 = dot convention) | Würth ANP047 |
| PWR-05 | No sensitive nets under or next to the inductor or SW on any layer | Keep-out = L courtyard + ≥1–2 mm; SW clearance to FB ≥ ~1 mm (heuristic) | Magnetic and capacitive coupling into high-Z nets | FB, COMP, RT, SS, sense, clocks, RF | S1 (FB) | Rule area under L (no tracks of net class "sensitive"); parallel-run length of FB within X mm of SW | HS Electronik, NextPCB, AAC |
| PWR-06 | FB/VOS sensed at the COUT pad (Kelvin); divider next to the FB pin | Divider within ~2–3 mm of FB (heuristic); FB high-Z segment shortest | The high-Z node picks up noise; sensing at COUT avoids IR and ripple error | All regulators | S1 | FB-divider top resistor connects to VOUT by a trace starting at the COUT pad (not the inductor pad); FB-node trace length | TPS62130 DS, SLYT614 |
| PWR-07 | AGND island for small-signal parts, tied to PGND at one point (exposed pad), not in the hot-current path | One tie, at the IC EP / datasheet-specified point | Keeps PGND IR drop and di/dt noise out of the reference | Controllers with AGND/SGND pins | S2 | Net-tie footprint count == 1; AGND zone not overlapping hot-loop polygon | TPS62130 DS, SLYT614 step 5, SchematicsHub |
| PWR-08 | COUT return near CIN return (buck), so AC current closes locally | COUT GND pad within a few mm of CIN GND pad | Ripple-current loop area | Buck | S3 | Distance between COUT GND pad and CIN GND pad | AN-139 (CIN→COUT AC path) |
| PWR-09 | Boost: COUT_HF tight to the rectifier and PGND | Same as PWR-01 | Pulsating output current | Boost, flyback secondary | S1 | Hot-loop area {LS FET, D, COUT_HF} | SNVA731, SLVA773 |
| PWR-10 | Use vias in the power path only in parallel arrays | ≥1 via per A (SLVA773); see section 2 via ampacity | Via R and L; current crowding | Any via in a power path | S2 | Count vias per net transition ≥ ceil(I/I_via) | SLVA773 |
| PWR-11 | Gate loops: driver next to the FET, gate and return routed as a pair, Kelvin source if available | Driver-to-gate trace length short (EPC: wide, short) | Common-source inductance causes false turn-on and ringing | Discrete FETs, GaN | S1 | Gate trace length; gate/return separation; check the Kelvin pin is used | EPC WP008, TI SLYP754 |
| PWR-12 | Bootstrap cap at the BOOT/SW pins, VDD bypass at the driver pins, smallest nearest | Shortest possible; C_boot ≈ 10× Qg-equivalent | High peak charging current | Half-bridges | S2 | Pad distance cap↔pins | TI SLUA887, SLUAAM3 |
| PWR-13 | Snubber (RC on SW; RCD clamp on flyback drain) in the tightest loop across the switching element | Snubber pads adjacent to the switch pins | Snubber loop inductance defeats the snubber | When fitted | S2 | Loop area {snubber R, C, switch pins} | SLYT614 step 2, Infineon AN-1195 |
| PWR-14 | Current-sense: 4-wire Kelvin, equal-length pair to the amplifier, amplifier near the shunt, same side | Sense taps on the inner/centre of the pads | IR drop in pads and solder is comparable to the shunt voltage | Shunts ≤ ~100 mΩ | S1 | Sense nets as diff pair; length mismatch; tap point inside pad region | onsemi DN05117, Bourns |
| PWR-15 | Exposed-pad thermal vias | 0.3 mm drill, 1.0–1.2 mm pitch; plugged/tented/filled | Thermal conduction to inner planes | QFN/DFN power ICs | S2 | Count and pitch of vias inside the EP polygon; via fill attribute | TI SLOA122, Renesas TB389 |
| PWR-16 | LDO: CIN/COUT at the pins; output through COUT before branching; size copper for P = (VIN−VOUT)·I | Copper area from θJA; ~2 cm²/W first guess (low authority) | Stability (ESR), transient, junction temperature | LDOs | S2 | Pad distances; copper area of the GND/thermal net around EP vs computed P | Renesas, PCBWay |
| PWR-17 | Feedback and compensation parts on the side of the IC away from SW and L | — | Geometric separation from aggressors | All | S2 | Angular sector test: FB components not in the SW/L half-plane of the IC | SLYT614 step 4 (small signal), inference |

**Myths and context-dependent points (power):**
- "Star ground everything" is context-dependent. On multilayer boards the solid plane plus correct placement (hot loop local, AGND island, single tie) is what the TI and ADI notes show. A literal star of traces adds inductance.
- "Copper under the inductor": sources conflict (TI vs HS Electronik). Follow the datasheet. Default: keep the top-layer pour out from under unshielded inductors, keep the L2 ground solid.
- "Bigger SW copper for cooling" is wrong. Spread heat with vias from PGND or the EP instead.

### Gaps
- Exact numeric content of SLYT614 steps 2–5, AN-136 and AN-139 (loop-area figures, nH values, via counts) could not be read directly because the PDFs were blocked.
- No authoritative numeric maximum for hot-loop area or SW copper area was found. A target of 1 cm² for a boost appears only on a low-authority calculator page.
- MPS and Würth "ANP" notes on hot-loop layout beyond ANP047, and Bob Pease and Jim Williams material, were not reachable or found in this session.
- No primary source confirmed whether the shunt sense tap should be at the pad's inner edge or its centre. Use the shunt's datasheet land pattern.

---

## 2. Decoupling and PDN: placement, vias, plane capacitance, target impedance, bulk vs local, ferrite beads, trace width vs current, voltage drop

### Takeaway
What sets high-frequency decoupling performance is mounting loop inductance (pads, vias, distance to the plane pair), not the capacitor's value. "Smallest value closest" is a proxy that works only because small values usually come in small packages. Design the PDN against a target impedance (Z_t = ΔV/I_transient). Derate MLCCs for DC bias, run ferrite beads at a small fraction of rated current with resonance damped, and size traces and vias with IPC-2152 (or the more conservative IPC-2221) plus an explicit IR-drop check.

### Cited Findings
- Bogatin, Smith and Sandler, "The Myth of Three Capacitor Values" (2020): the three-value rule rests on 50-year-old assumptions. Lower mounting loop inductance always helps. Place MLCCs early so they can be routed with the lowest practical mounting inductance. — [Signal Integrity Journal](https://www.signalintegrityjournal.com/articles/1589-the-myth-of-three-capacitor-values)
- Bogatin: 0.1 µF and 47 µF MLCCs in the same body size have the same ESL. Low mounting inductance is the most important selection criterion. — [Passive Components EU, Bogatin](https://passive-components.eu/a-low-cost-capacitor-characterization-system/)
- Altium: mounting inductance (ESL plus pads and vias) does not change with location, but the spreading/path inductance through the planes depends on location. — [Altium "When does decoupling capacitor location matter"](https://resources.altium.com/p/when-does-decoupling-capacitor-location-matter-pcb)
- Archambeault's IEEE EMC chapter talk "PCB Power Decoupling Myths Debunked" covers the same theme (full text not extracted here). — [Archambeault slides](https://ewh.ieee.org/r3/enc/emcs/archive/2012-10-10b_DecouplingMyths.pdf)
- Wikipedia states the conventional rule: the smallest-value caps go closest to the consumer to minimize AC loop area. — [Wikipedia: Power integrity](https://en.wikipedia.org/wiki/Power_integrity)
- Measured mounting inductance of a 0402 decoupling cap: via-in-pad ≈ 0.44 nH (top side) vs 0.63 nH with short surface traces to vias. Bottom side: 1.04 vs 1.35 nH. Overplated via-in-pad gives a 15–30% reduction. — [Axotron: inductance of decoupling layouts](https://axotron.se/blog/inductance-of-some-decoupling-layouts/); [Axotron: more measurements](http://axotron.se/blog/more-decoupling-layout-inductance-measurements/)
- Via-in-pad lowers via-to-plane distance and so mounting inductance, but it can thieve solder in manufacturing and costs more (filled and plated over). — [USPTO 7312402](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7312402)
- Target impedance: Z_target = ΔV_allowed / I_transient. Example: a 1 V rail with 5% (50 mV) ripple and a 10 A step needs 5 mΩ. The target must hold at every frequency where transient current exists. The VRM covers up to roughly 100 kHz, board caps the middle band, and on-package/on-die caps cover roughly ≥50 MHz. Board mounting inductance sets a floor below which adding caps stops helping. — [ICD Target Impedance (Design007, 2018)](https://www.icd.com.au/articles/TargetZ_Design007-Feb2018.pdf); [MPS "Meeting the Impedance Mask"](https://media.monolithicpower.com/mps_cms_document/a/i/aip_meeting-the-impedance-mask_strategies-for-pdn-design-and-optimization_r1.0.pdf); [Altium PDN Simulation Guide](https://files.resources.altium.com/sites/default/files/2022-02/PDN%20Simulation%20and%20Analysis%20Guide.pdf); [JLCPCB PDN blog](https://jlcpcb.com/blog/pdn-impedance-high-performance-pcb)
- Because transient current is rarely known exactly, the usual approach is to design to an impedance profile. X7R DC-bias derating can leave delivered capacitance 30–70% below nominal. — [MPS impedance mask](https://media.monolithicpower.com/mps_cms_document/a/i/aip_meeting-the-impedance-mask_strategies-for-pdn-design-and-optimization_r1.0.pdf); [JLCPCB PDN blog](https://jlcpcb.com/blog/pdn-impedance-high-performance-pcb)
- MLCC DC bias: a 0402/0603 X7R at 50–60% of rated voltage can lose about 30–50%, against 10–20% for 1206/1210. In one example a 10 µF 6.3 V 0402 X5R behaves like about 1.5 µF at 5 V. A common derating starting point is 50% of rated voltage. — [Ultra Librarian MLCC selection](https://www.ultralibrarian.com/2026/03/05/mlcc-capacitor-selection-ulc); [Octopart "Breaking down MLCC surprises"](https://octopart.com/pulse/p/breaking-down-mlcc-surprises); [Utmel DC-bias derating](https://www.utmel.com/blog/categories/capacitors/mlcc-dc-bias-derating-how-to-calculate-and-compare-effective-capacitance-before-component-selection)
- Ferrite beads (ADI AN-1368): datasheet impedance is given at zero DC bias. Operate around 20% of rated DC current, because the rating is a temperature-rise limit and not a filtering operating point. In AN-1368's example, a bead plus a 10 nF capacitor resonated near 2.5 MHz and produced about 10 dB of gain at a 2.4 MHz ripple instead of attenuation. Damp it with a parallel resistor across the bead or series resistance with the cap. — [ADI AN-1368](https://www.analog.com/en/resources/app-notes/an-1368.html); [Power Systems Design summary](https://www.powersystemsdesign.com/articles/ferrite-bead-demystified/95/10031); [Altium ferrite bead article](https://resources.altium.com/p/how-use-ferrite-bead-your-design-reduce-emi)
- Steve Weir's slides (from manufacturer data) say impedance can drop substantially above 30–40% of rated DC current. — [Weir, PDN Application of Ferrite Beads](https://emcfastpass.com/wp-content/uploads/2017/04/PDN_Ferrite_Beads.pdf)
- Trace current: IPC-2221 uses I = k·ΔT^0.44·A^0.725 (A in mil², k = 0.048 external, 0.024 internal). IPC-2152 is chart-based with corrections for copper weight, board thickness and plane proximity. It usually permits more current, and it showed internal traces near planes are not as derated as IPC-2221 implied. A plane within about 0.5–1 mm acts as a heatsink. — [semiconductor.tools IPC-2221 vs 2152](https://semiconductor.tools/blogs/07-ipc-2221-vs-ipc-2152); [tracewidthcalculator.com](https://tracewidthcalculator.com/blog/ipc-2221-vs-ipc-2152-pcb-standards/)
- Per the IPC-2221 formula, 1 A at a 10 °C rise on 1 oz external copper needs about 0.30 mm (11.8 mil). Some blogs quote 20 mil, which does not match the formula. — [100nF trace width tool](https://100nf.com/tools/trace-width/)
- Via ampacity: a 0.3 mm via with 25 µm plating carries about 1.9 A at a 10 °C rise (IPC curve fit), or about 1.6 A with 20 µm plating. Other sources say 0.8–1.0 A, so use the conservative value. Resistance is about 1.1 mΩ per via in a 1.6 mm board. Plating thickness matters more than drill size. — [semiconductor.tools via current](https://semiconductor.tools/blogs/12-pcb-via-current-capacity); [QueenEMS via capacity](https://www.queenems.com/blog/pcb-via-current-capacity/); [tracewidthcalculator 0.3 mm](https://tracewidthcalculator.com/via-current/0.3mm-2via)
- Return-path continuity: put ground stitching vias next to signal vias that change reference plane. One vendor says at least two within 50 mil, another says one within 1 mm. Where the reference changes between power and ground planes, add stitching capacitors. — [Sierra Circuits high-speed routing](https://www.protoexpress.com/blog/best-high-speed-pcb-routing-practices/); [Cadence return paths](https://resources.pcb.cadence.com/blog/grounding-and-return-paths-power-plane-no-nos); [zbotic ground stitching](https://zbotic.in/pcb-ground-plane-pour-split-and-stitching-strategy/)

### Inferences

| ID | Rule | Numeric guideline | Why | Applies | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|---|
| PDN-01 | Each IC power pin gets a local HF cap whose GND and PWR vias sit at the pads (via-in-pad or vias on the pad's long sides), on the side nearest the IC | Cap pad-edge to pin pad ≤ ~2–3 mm (heuristic); via-to-pad trace ≤ ~0.5 mm; ≥1 via per pad | Mounting loop inductance dominates above self-resonance | Digital ICs, MCU/FPGA, ADC | S2 | For each power pin: nearest cap on the same net pair, distance; via count and distance per cap pad | Bogatin, Axotron, Altium |
| PDN-02 | Order the caps by mounting inductance, not by value: the lowest-L package goes nearest the highest-di/dt pins; bulk caps anywhere on the rail plane near the IC group | Bulk within the "local" region (heuristic ~10–20 mm) | Location-independent mounting L vs location-dependent spreading L | Multilayer with planes | S3 | Classify caps by package; check the smallest package is closest | Bogatin, Altium |
| PDN-03 | Keep the power and ground plane pair close (thin dielectric) in the stackup | Plane-pair capacitance ≈ ε0·εr·A/d ≈ 38 pF/cm² at d = 0.1 mm, εr = 4.3 (calculated) | Plane capacitance and low spreading inductance give HF decoupling | ≥4 layers | S3 | Stackup check: PWR/GND adjacency and dielectric thickness | Physics |
| PDN-04 | Compute Z_target for each rail and pick cap count and values from the impedance profile, not "0.1 µF per pin" | Z_t = ΔV/ΔI | Ensures adequate impedance from VRM bandwidth up to package frequencies | High-current digital rails | S3 | Sum of cap admittances, using DC-bias-derated C, vs Z_t (simple RLC model) | ICD, MPS |
| PDN-05 | Derate MLCC capacitance at the operating DC bias before counting it | Check vendor curves; 50% voltage derating starting point | Class II ceramics lose C under bias | All X5R/X7R | S2 | BOM check: V_rail / V_rated and package → expected loss | Ultra Librarian, Octopart |
| PDN-06 | Ferrite bead only where needed (isolating an analog or RF rail), with I_DC ≤ ~20% of rated, and a damping check on the bead + cap resonance against known noise frequencies (for example the SMPS f_sw) | f_res = 1/(2π√(L_bead·C)) must not land near f_sw | Saturation and LC peaking | Analog, PLL, RF rails | S2 | Compute f_res from the bead's L (datasheet) and downstream C; flag if within ±50% of f_sw | ADI AN-1368 |
| PDN-07 | Size power traces and pours with IPC-2152/2221 and check IR drop | ΔV = I·R, R = ρ·L/(w·t); ρ_Cu ≈ 1.72e-8 Ω·m; 1 oz ≈ 35 µm | Heating and regulation error at the load | All power nets | S2 | Per net: min width on the current path vs I_max (from regulator rating); IR-drop along path | IPC-2221 formula |
| PDN-08 | Never cut a plane under signals that reference it; stitch at layer changes | ≥1–2 GND vias within ~1 mm of each signal via that changes reference | Return current follows the signal; a gap makes a large loop | All | S2 | For each via on a signal net, nearest GND via distance; check track crossing zone voids | Sierra, Cadence, Ott (sec. 4) |

**Myth notes (PDN):**
- "Smallest value closest": a partial myth. The real rule is "lowest mounting inductance closest". In the same package, a 10 µF and a 100 nF cap have the same ESL (Bogatin).
- "Use 3 values per pin (100 nF / 10 nF / 1 nF)": a myth per Bogatin et al.; it can create anti-resonances.
- "Ferrite beads on every rail": often harmful (resonance, saturation, DC drop); context-dependent.
- "Decoupling location doesn't matter": context-dependent. It matters less on boards with tightly coupled planes at frequencies where spreading inductance is small compared with mounting inductance (Altium framing). It matters on 2-layer boards without planes.

### Gaps
- I could not extract Archambeault's quantitative conclusions or the full Bogatin article text.
- I found no authoritative numeric "max distance from cap to pin". All mm figures above are heuristics to be calibrated, ideally with a quick loop-inductance estimate per placement.
- I did not verify the IPC-2152 chart values themselves (the standard is paywalled). The calculator sources disagree with each other.

---

## 3. RF: controlled impedance, CPWG, short and straight RF traces, matching at pins, via fences, antenna keep-outs, shielding, separation from switchers and clocks, stitching density, stubs, bends

### Takeaway
Treat RF as fixed geometry dictated by the module or RF-IC datasheet and reference design. That means a 50 Ω CPWG over a continuous ground, the matching network right at the RF pin, the shunt elements grounded at the RF ground pin, and ground-via fences at ≤ λ/20 (u-blox: ≤2 mm pitch, ≤0.5 mm from the coplanar ground edge). The antenna keep-out zone must be free of copper on every layer, with the module at the board edge (Espressif: ≥15 mm clearance in all directions). Keep switchers and clocks well away (vendor heuristic: ~20 mm) or shield them. Mitering 90° bends matters only at multi-GHz.

### Cited Findings
- Via fence pitch < λ/20 at the maximum frequency, where λ is the wavelength in the substrate (guided). This makes the fence look solid and minimizes loading on the line. Single-via self-resonance is typically a few hundred MHz to a few GHz. — [Wikipedia: Via fence](https://en.wikipedia.org/wiki/Via_fence); [arXiv 2012.01438 (microwave package design)](https://arxiv.org/pdf/2012.01438); [RF Essentials CPWG glossary](https://rfessentials.com/resources/rf-glossary/cpwg/)
- At 77 GHz, λ/20 is about 0.1 mm, which approaches standard drill limits, so microvias may be needed (vendor). — [AtlasPCB GCPW](https://www.atlaspcb.com/blog/gcpw-coplanar-waveguide-pcb-design-rf-mmwave/)
- u-blox integration manuals: design RF lines for 50 Ω, with coplanar microstrip the most common. Put ground vias no more than 0.5 mm from the coplanar ground edge, at no more than 2 mm pitch. Use trace width ≥200 µm for impedance control. Keep the trace ≥3× its width from the ground-plane edge ("3W"). Do not route the RF trace under the module, where the ground distance is small and poorly controlled. Keep the entire stack below the RF connection free of digital lines. Void ground under the U.FL signal pad on at least the first inner layer. Carry ground ≥10 mm beyond the module on the three non-edge sides (one manual). — [u-blox NORA-B2 SIM](https://content.u-blox.com/sites/default/files/documents/NORA-B2-u-connectXpress_SIM_UBXDOC-465451970-3906.pdf); [u-blox MAX-M5Q HIM](https://content.u-blox.com/sites/default/files/MAX-M5Q_HardwareIntegrationManual_(UBX-13002460).pdf); [u-blox LEA/NEO/MAX-6 HIM](https://content.u-blox.com/sites/default/files/products/documents/LEA-NEO-MAX-6_HIM_(UBX-14054794)_1.pdf); [u-blox ANNA-B4 SI](https://www.mouser.com/pdfDocs/ublox_ANNA-B4_SI.pdf)
- Nordic nRF52: the radio output impedance is not 50 Ω, so a matching network is required between ANT and the 50 Ω reference point; it also filters the 2nd and 3rd harmonics. On QFN, ground the shunt capacitor nearest the radio through the VSS pin nearest ANT. The 50 Ω line should be coplanar waveguide, with W and G from a calculator. — [Nordic DevZone: general PCB design guidelines for nRF52](https://devzone.nordicsemi.com/guides/hardware-design-test-and-measuring/b/nrf5x/posts/general-pcb-design-guidelines-for-nrf52-series)
- Nordic staff on DevZone: continuous ground under the centre pad and the whole RF path, a 4×4 via grid from the centre pad to bottom ground, and no ground plane under the antenna. — [Nordic DevZone layout review](https://devzone.nordicsemi.com/f/nordic-q-a/83839/nrf52832-layout-review-and-antenna-design)
- A third-party blog suggests ground vias every ~2 mm around the RF section and decoupling within ~2 mm of module power pins (low authority). — [zbotic RF matching](https://zbotic.in/pcb-for-rf-antenna-matching-and-transmission-line/)
- Espressif ESP32: at least 15 mm clearance in all directions for the PCB antenna inside the housing. Do not put the module mid-board with cut-outs on four sides. Put the antenna feed as close to the board edge as possible. Consider cutting away the base board beside and below the antenna. Put sufficient ground copper and dense ground vias near the antenna. Test throughput and range on the final product. — [Espressif ESP32 HW design guidelines, PCB layout](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html); [Espressif PDF](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/esp-hardware-design-guidelines-en-master-esp32.pdf)
- One third-party review uses a looser 10 mm no-copper zone around the antenna edges. It conflicts with Espressif, so use the module vendor's figure. — [ESP32-S2 review](https://industrialmonitordirect.com/blogs/knowledgebase/esp32-s2-pcb-design-review-critical-issues-and-fixes)
- RF separation and shielding (vendor/knowledge-base level): about 20 mm between a switching regulator and RF is a practical starting point, and dense boards need via fences or shield cans. Put the LNA input as far from SMPS as possible, because harmonic spurs desensitize it. Shield-can footprint: a continuous 0.5–1.0 mm ground pad ring with vias at ≤1.0 mm pitch to the inner ground. Via fence ≥3× substrate height from the trace edge. Use double staggered rows for TX/RX isolation. Quoted shield effectiveness of 30–70 dB is a rough vendor estimate. — [RF Essentials: RF-digital EMI](https://rfessentials.com/rf-knowledge-base/how-do-i-design-a-pcb-layout-to-minimize-electromagnetic-interference-between-rf/); [RF Essentials: shielded compartment](https://rfessentials.com/rf-knowledge-base/how-do-i-design-a-shielded-compartment-on-a-pcb-to-isolate-sensitive-rf-stages/); [AtlasPCB EMC shielding](https://www.atlaspcb.com/blog/emc-shielding-pcb-via-fence-ground-plane/)
- 90° bends: the myth traces to one figure in the 1971 Motorola MECL handbook. Per Altium, Bogatin's S-parameter data showed no noticeable effect for a 5-mil trace until well over 70 GHz. A simulation found a 20 dB improvement from a mitered bend at 77 GHz. An amateur analysis suggests mitering becomes worthwhile around 5.8 GHz, with round corners above that. Acute angles (<90°) are a fab acid-trap concern. — [Altium "Slaying the 90° bend dragon"](https://resources.altium.com/p/slaying-900-right-angle-bend-dragon); [Georgia Tech ECTC09 (Rida)](https://tentzeris.ece.gatech.edu/ECTC09_Rida.pdf); [theantennaguy: 90-degree angles](https://theantennaguy.github.io/90-degree-angles/)

### Inferences

| ID | Rule | Numeric guideline | Why | Applies | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|---|
| RF-01 | 50 Ω (or the specified Z0) CPWG/microstrip; width and gap computed from the stackup; continuous ground on the reference layer under the full line | Width from field solver; u-blox ≥200 µm | Impedance mismatch causes reflection and loss | All RF nets | S1 | Net class "RF50": width/gap equals computed values; no zone voids or other nets on the reference layer under the trace | u-blox, Nordic |
| RF-02 | Shortest, straightest RF path; no stubs, test pads or T-branches except designed matching elements | Stub length ≪ λ/10 (heuristic) | Stubs are resonant and add capacitance | RF | S1 | RF net topology must be point-to-point through series parts; detect branches | Physics |
| RF-03 | Matching network at the RF pin, with series parts in line and shunt parts grounded at the RF-ground pin or vias next to the pad | First element within ~1 mm of the pin (heuristic) | Pin-to-match line acts as an unintended transmission-line section | RF ICs | S1 | Distance from the RF pin to the first matching pad; shunt-cap GND via distance | Nordic |
| RF-04 | Via fence along CPWG and around the RF section | Pitch ≤ min(λ_g/20, 2 mm); via ≤0.5 mm from the ground edge | Suppresses parallel-plate and coplanar modes; isolation | RF, ≥2 layers | S2 | Along the RF trace: max gap between consecutive GND vias within X mm of the trace edge | Wikipedia, u-blox |
| RF-05 | Antenna keep-out: no copper (tracks, zones, vias) on any layer within the module or antenna vendor's keep-out; module at the board edge, antenna overhanging or at the edge | Espressif ≥15 mm clearance; module-specific keep-out polygon | The ground plane detunes the antenna and lowers efficiency | PCB/chip antennas | S1 | KiCad rule area (keepout, all layers) from the footprint; DRC; board-edge distance of the feed | Espressif, Nordic, u-blox |
| RF-06 | Separate RF from SMPS, clocks and high-speed digital; shield or fence if dense | ~20 mm start (low authority); or a shield can with a ≤1 mm via-pitch ring | Harmonics of f_sw and clocks desensitize the receiver | Receivers, LNAs, GNSS | S2 | Distance between the RF block bounding box and switcher hot-loop / clock nets | RF Essentials |
| RF-07 | No digital or power routing on any layer under RF lines or the matching network | — | Coupling and reference disruption | RF | S2 | Layer stack under RF polygons contains only GND | u-blox |
| RF-08 | Bends: arcs or mitered corners on RF nets above a few GHz; any corner fine below ~1 GHz; never acute angles | Miter ≈ 50–60% of the corner diagonal (classic optimal-miter value, not verified here) | Excess corner capacitance matters only when the corner is a non-trivial fraction of λ | RF ≥ ~3–5 GHz | S4 (<1 GHz), S3 (>5 GHz) | Detect 90° vertices on RF nets; acute-angle check on all nets | Altium, GaTech |
| RF-09 | Ground pour stitching density on general boards | Pitch ≤ λ/20 at the highest significant frequency (λ/10 is a looser common variant) | Avoids slot or patch resonances in the pour | Pours near RF/high-speed | S3 | Max distance between stitching vias in each pour | Wikipedia |

Worked λ/20 values, computed with εr ≈ 4.3 (stripline-like; a microstrip's εr_eff is lower, so its λ is longer and these figures are conservative): λ0 at 2.4 GHz = 125 mm → λ_g ≈ 60 mm → λ_g/20 ≈ 3.0 mm, λ_g/10 ≈ 6 mm. At 5.8 GHz: λ_g ≈ 25 mm → λ/20 ≈ 1.25 mm. At 1 GHz: λ_g ≈ 145 mm → λ/20 ≈ 7.2 mm. u-blox's 2 mm cap is therefore stricter than λ/20 at 2.4 GHz and looser than λ/20 at 5.8 GHz.

**Myth notes (RF):**
- "Never use 90° corners" is a myth for digital and below ~1 GHz (Bogatin data via Altium). It matters at mmWave.
- "λ/10 vs λ/20 stitching": both are rules of thumb. λ/20 at the highest harmonic of concern is the common conservative choice.

### Gaps
- I could not read Nordic module (nRF52/nRF54) keep-out dimension figures or u-blox antenna cut-out figure values from the extracts. Each keep-out polygon must be pulled from the specific module datasheet.
- I found no authoritative numeric separation distance between SMPS and RF. The 20 mm figure is from a knowledge-base site.
- I did not obtain an optimal miter percentage from a source.

---

## 4. Analog and mixed-signal: partitioning, ground strategy, ADC/DAC AGND/DGND, references and op-amp feedback, guard rings, Kelvin shunts, thermal gradients, crystals

### Takeaway
Use one solid ground plane and partition placement and routing so that analog and digital return currents never share a region (Ott, TI). Don't split the plane. If a split is forced, bridge it at the ADC and route every crossing trace over the bridge. Treat low-digital-current ADCs and DACs as analog parts, with AGND and DGND both tied to the analog ground at the package (ADI MT-031). Guard high-Z nodes with a ring driven at the node's potential, with no solder mask over it. Put crystals right at the MCU with symmetric load caps, a grounded guard and no noisy routing nearby (ST AN2867).

### Cited Findings
- Henry Ott: if you split the ground plane and route traces across the split, the return current has no nearby path, so it flows in a large loop that radiates and adds ground inductance. His preferred approach is a single ground plane with the board partitioned into analog and digital routing sections, with ADCs straddling the partition. If a split is required, connect the planes at one place (a bridge) and route all crossing traces over it. — [Ott tech tip: Grounding of Mixed Signal PCBs](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html); [Ott, EE Times "Partitioning and Layout of a Mixed-Signal PCB"](https://www.eetimes.com/partitioning-and-layout-of-a-mixed-signal-pcb-3/)
- TI agrees that it is always preferable to use one ground plane and partition the PCB. The main risk is analog signals routed into the digital section or the reverse. — [TI SLYT512](https://www.ti.com/lit/an/slyt512/slyt512.pdf)
- ADI MT-031: ADCs and DACs (and other mixed-signal ICs) with low digital currents should be treated as analog parts, grounded and decoupled to the analog ground plane. Connecting DGND to a separate digital plane puts V_noise across AGND and DGND. — [ADI MT-031](https://www.analog.com/mt-031); [ADI EngineerZone discussion](https://ez.analog.com/data_converters/precision_adcs/f/q-a/25925/separating-agnd-and-dgnd-at-the-adc-dac)
- TI: join AGND and DGND externally to the same low-impedance plane with minimum lead length, because extra DGND impedance couples digital noise into the analog input. — [TI SLYT499](https://www.ti.com/lit/pdf/SLYT499)
- ADI engineers note that the right option depends on the device and application: two planes joined at one point, or multiple joins that mimic a solid plane. Some multi-device datasheets (for example AD5522) specify their own scheme, so the datasheet and eval-board layout come first. — [ADI EngineerZone](https://ez.analog.com/data_converters/precision_adcs/f/q-a/25925/separating-agnd-and-dgnd-at-the-adc-dac)
- Guard rings: drive the guard from a low-impedance source at the same potential as the sensitive node. For inverting configurations tie the guard to +IN potential, for non-inverting to −IN. Do not cover the guard with solder mask, and guard both sides of the board if needed. Guarding nearly eliminates surface leakage but reduces bulk leakage far less. — [Microchip leakage currents](https://developerhelp.microchip.com/xwiki/bin/view/products/amplifiers-linear/operational-amplifier-ics/precision-design/leakage-currents/); [ADI "Layout for Precision Op Amps"](https://www.analog.com/en/resources/technical-articles/layout-for-precision-op-amps.html); [TI AN-241 (LM108 high-Z op amps)](https://www.ti.com/lit/an/snoa664/snoa664.pdf)
- Thermal EMF: unevenly heated dissimilar-metal junctions (pads, solder, resistors, jumpers) generate thermoelectric voltages on the order of 200 nV/°C. Symmetric layout keeps paired junctions at the same temperature. — [Electronics360 precision op-amp layout](https://electronics360.globalspec.com/article/9981/pcb-layout-for-precision-operational-amplifiers)
- The inverting summing node is especially sensitive to parasitics because it sees both the input and feedback networks. — [TI "Op Amps for Everyone"](https://web.mit.edu/6.101/www/reference/op_amps_everyone.pdf)
- ST AN2867 (oscillators): mount the crystal as close as possible to the MCU with short traces. A grounded guard ring around the oscillator is essential against noise. Give the oscillator its own local ground plane connected to the nearest MCU ground. Do not connect a metal crystal can to the oscillator ground. Route high-frequency signals away from the oscillator. Keep the load caps symmetric. Load capacitance includes C_L1, C_L2 and PCB stray C_s. Coat LSE crystals in harsh humidity. — [ST AN2867](https://www.st.com/resource/en/application_note/an2867-guidelines-for-oscillator-design-on-stm8afals-and-stm32-mcusmpus-stmicroelectronics.pdf); [ECS copy of AN2867 Rev 19](https://ecsxtal.com/store/pdf/stm32-microcontroller-application-note.pdf)
- Kelvin shunts: see section 1 (onsemi, Bourns). Thermal coupling note: copper in the sensed current path adds temperature sensitivity. — [NextPCB current-sense guide](https://www.nextpcb.com/blog/current-sense-resistor-pcb-layout-kelvin-connection)

### Inferences

| ID | Rule | Numeric guideline | Why | Applies | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|---|
| AMS-01 | One continuous GND plane; partition placement into analog and digital regions; ADC/DAC straddles the boundary, analog pins facing the analog region | No GND-plane slots under signals | Return current flows under its trace; split gaps create loops | Mixed-signal | S2 | Region polygons from schematic blocks; detect analog-class tracks inside the digital region and vice versa; detect zone voids crossed by tracks | Ott, TI |
| AMS-02 | ADC/DAC AGND and DGND pins both go to the (analog) ground plane at the package with minimal length, unless the datasheet says otherwise | Via at the pad | DGND impedance couples digital noise into the analog input | Low-digital-current converters | S1 | Pins named AGND/DGND share net or connect by a net-tie at the package | MT-031, SLYT499 |
| AMS-03 | If planes are split (datasheet-mandated), one bridge at the converter, and every crossing trace routed over it | Exactly one AGND–DGND connection | A second tie makes a ground loop; crossings elsewhere have no return | Split designs | S1 | Count net-ties; for tracks crossing the split boundary, check they lie over the bridge polygon | Ott |
| AMS-04 | Converter decoupling to the analog ground at the pins; digital interface buffered/series-terminated near the converter | — | Keeps digital edge currents local | ADCs | S2 | PDN-01 check with an AGND reference | MT-031 |
| AMS-05 | Guard ring around high-Z inputs (≥ GΩ-class, electrometer, photodiode TIA), driven at the summing-node potential, mask opened, both sides | Ring encloses the input pin and the feedback-resistor high-Z end | Surface leakage | Inputs with I_bias ≲ nA–pA | S1 (for those circuits) | Ring track net == designated guard net; solder-mask opening layer present over ring | Microchip, ADI, TI AN-241 |
| AMS-06 | Feedback and input resistors adjacent to the op-amp inverting pin; minimize summing-node copper | Summing-node trace short (heuristic ≤ ~3 mm) | Stray capacitance at the summing node degrades phase margin and adds noise gain | Op-amps, especially fast or high-Z | S2 | Total copper length of nets connected to IN− pins | Op Amps for Everyone, inference |
| AMS-07 | Precision parts (reference, input pairs, matched resistors, shunt sense) placed symmetrically and away from heat sources; paired thermal junctions at equal temperature | Isotherm symmetry; keep away from regulators and power resistors | Thermal EMF ~200 nV/°C; resistor TCR mismatch; reference drift | Precision DC (<100 µV error) | S2 | Distance to parts with high estimated power; mirror-symmetry metric for matched pairs | Electronics360 |
| AMS-08 | Crystal within a few mm of the OSC pins; load caps symmetric next to the crystal; grounded guard; no foreign traces under or around it on the adjacent layer | Crystal-to-pin trace ≤ ~5 mm (heuristic); equal trace lengths | Stray C shifts frequency; injected noise causes jitter or stoppage | All crystals | S2 | Distance crystal pads ↔ MCU OSC pins; length match of XIN/XOUT; no other nets within keep-out polygon (all layers adjacent) | ST AN2867 |
| AMS-09 | Kelvin connections for all precision sense points (shunts, remote sense, reference returns) | See PWR-14 | IR drop in shared copper | Precision | S1 | Separate sense nets terminating at pad interior | onsemi, Bourns |

**Myth notes (AMS):**
- "Always split AGND and DGND planes" is largely a myth, or legacy datasheet text (Ott; TI SLYT512). Split only when the datasheet or a real constraint demands it, and then bridge once.
- "Connect DGND to the digital plane" is wrong for low-digital-current converters (MT-031).

### Gaps
- I did not reach ADI's "Layout for Precision Op Amps" in full text for numeric guard spacing. Guard-gap numbers that appeared (0.5 mm, 50 mil) came only from low-authority sites and are excluded.
- The ST AN2867 figure showing the recommended layout (including any "no traces under the crystal" rule) was not available as text.
- No source was found giving a numeric thermal-gradient budget for references.

---

## 5. Thermal: copper area, thermal vias, separation of heat sources from sensitive parts and electrolytics, airflow, spacing

### Takeaway
Heat moves easily along copper planes but poorly through FR-4. Carry heat from exposed pads into inner and bottom planes with arrays of about 0.3 mm vias at 1.0–1.2 mm pitch (plugged or tented). Spread heat sources apart, keep them out of corners, and keep electrolytics, crystals, references and other temperature-sensitive parts upstream of the airflow and away from hot spots. Electrolytic life roughly halves for every 10 °C rise (liquid-electrolyte types only).

### Cited Findings
- Thermal via geometry: 0.3 mm or less at 1 mm pitch (TI SLOA122). A 1.0–1.2 mm pitch grid, 0.3–0.33 mm diameter, about 1 oz barrel, connected to buried planes, with diminishing returns as more are added (Renesas TB389). Tent with solder mask at least 0.10 mm larger than the via diameter if not plugged (NXP AN1902). — [TI SLOA122](https://www.ti.com/lit/pdf/sloa122); [Renesas TB389](https://www.renesas.com/en/document/oth/tb389-pcb-land-pattern-design-and-surface-mount-guidelines-qfn-packages); [NXP AN1902](https://www.nxp.com/docs/en/application-note/AN1902.pdf)
- Per-via thermal resistance is about 150 °C/W for a 0.3 mm via with 25 µm plating in a 1.6 mm board (R = L/(kA), k = 385 W/m·K). A 9-via array gives roughly 17–33 °C/W. Filled vias (IPC-4761 Type VII) cut it substantially (calculator claims 6–8×). — [rftools via thermal resistance](https://rftools.io/calculators/pcb/via-thermal-resistance/); [semiconductor.tools via current](https://semiconductor.tools/blogs/12-pcb-via-current-capacity)
- PCB stackups are thermally anisotropic. Use planes plus vias to build 3-D heat paths. — [Salitronic thermal management](https://salitronic.com/kb/thermal-management/)
- Placement (vendor guidance, low to medium authority): do not put a tall component upstream of a hot one (a 10 mm electrolytic was cited as creating a stagnant wake). Keep sensitive parts (electrolytics, crystals, references) on the cool upstream side. Align tall parts with the airflow. Separate high-power parts rather than clustering them (two 2 W parts 5 mm apart share one copper patch and their rises add; 5–10 mm suggested as a start). Keep hot parts away from board corners, where copper cannot spread heat. — [NextPCB thermal design basics 2](https://www.nextpcb.com/blog/pcb-thermal-design-basics-2-component-layout); [ALLPCB thermal-aware placement](https://www.allpcb.com/blog/pcb-assembly/thermal-aware-component-placement-a-guide-to-preventing-overheating-on-pcbs.html); [EMA placement best practices](https://www.ema-eda.com/ema-resources/blog/best-practices-for-pcb-component-placement-emd/)
- Electrolytic life follows an Arrhenius-like 10 °C rule (life roughly doubles for each 10 °C cooler), but this is a simplification that ignores voltage and ripple. Polymer capacitors use a different, lab-derived rule. A worked example assumed +35 °C for a cap near IGBTs plus ripple heating. — [CapXon Lifetime Compendium](https://www.capxongroup.com/files/Lifetime%20Compendium_EN.pdf); [DigiKey TechForum lifetime calculation](https://forum.digikey.com/t/calculating-the-operational-life-of-an-aluminum-electrolytic-capacitor/45517)
- Copper pour example: 2 in² of copper reduced component temperature by 10–15 °C (vendor example, illustrative). — [JLCPCB heat dissipation guide](https://jlcpcb.com/blog/pcb-heat-dissipation-guide)
- Exposed-pad paste: use 50–80% paste coverage in multiple smaller apertures (Maxim/ADI), typically 50–70% (TI SLUA271, pSemi). A 1:1 aperture can float the part and cause opens (TI). Thermal-pad voiding ≤25% per IPC-A-610 (pSemi). — [Maxim QFN guidelines (ADI)](https://www.analog.com/en/resources/app-notes/smt-assembly-and-pcb-design-guidelines-for-maxims-standard-wirebonded-quad-flatpack.html); [TI SLUA271](https://www.ti.com/lit/slua271); [pSemi AN62](https://www.psemi.com/pdf/app_notes/an62.pdf)

### Inferences

| ID | Rule | Numeric guideline | Why | Applies | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|---|
| TH-01 | Exposed pad → via array to GND/thermal planes on ≥2 layers | 0.3 mm drill, 1.0–1.2 mm pitch; count ≈ EP area / pitch² | Vertical conduction; 150 °C/W per via means many in parallel | Packages with EP and P ≳ 0.3 W | S2 | Via count and pitch in the EP; connected zone area on other layers | TI, Renesas |
| TH-02 | Via fill or tent strategy compatible with assembly | Tent ≥ via + 0.1 mm, or plugged (IPC-4761) | Solder wicking causes voids and opens | EP vias | S3 | Via attribute / mask expansion check | NXP AN1902 |
| TH-03 | Windowpane paste on EPs | 50–70% coverage | Floating, voids | EPs > ~2×2 mm | S3 | Paste-layer area / pad area | TI SLUA271, Maxim |
| TH-04 | Copper area per dissipating part sized from P and θ | Start from the datasheet θJA test board; ~2 cm²/W heuristic (low authority) | Junction temperature limit | Regulators, FETs, resistors | S2 | Estimate P per part (LDO: (Vin−Vout)·I; resistors: I²R); compare connected copper area | PCBWay LDO, physics |
| TH-05 | Spread heat sources; keep them away from corners and from each other | ≥5–10 mm between >1 W parts (vendor heuristic) | Overlapping thermal spreading footprints | Multiple hot parts | S3 | Pairwise distance of parts with P > threshold | NextPCB |
| TH-06 | Temperature-sensitive parts (Al-electrolytics, crystals, references, precision analog, battery, sensors) away from and upstream of hot parts | ≥10 mm or outside the estimated hot-spot radius (heuristic) | Arrhenius life; drift | All | S2 | Distance from sensitive class to hot class; airflow direction if specified | CapXon, NextPCB |
| TH-07 | Tall parts parallel to airflow and not upstream of hot parts | — | Wake/shadowing | Forced air | S3 | Given an airflow vector: no tall part (> h) within upstream cone of a hot part | NextPCB |
| TH-08 | Don't use SW-node copper as a heatsink; use PGND/EP copper and vias | — | EMI (see PWR-03) | Switchers | S2 | SW-net copper area cap | Rohm, HS Electronik |

### Gaps
- No primary manufacturer number was found for minimum distance between an electrolytic and a heat source. All distances above are heuristics.
- No authoritative copper-area vs θJA curves were extracted (e.g., TI's thermal application notes on copper area could not be retrieved).

---

## 6. DFM, DFA and mechanical: spacing and courtyards, polarity orientation, one vs two sides, edge and hole keep-outs, fiducials, test points, tombstoning, panelization, connectors, height, silkscreen, fab limits (JLCPCB)

### Takeaway
Encode fab limits as DRC minimums but design to the recommended values, not the absolute minimums. For JLCPCB 1 oz that means 4/4 mil (2-layer), 3.5/3.5 mil (multilayer), annular ring 0.25 mm (2-layer) or 0.20 mm (multilayer), and copper ≥0.2 mm from routed edges. Use IPC-7351 courtyards (Level B 0.25 mm excess). Keep passives' thermal connections symmetric to prevent tombstoning. Provide 3 global fiducials (1 mm copper, 2 mm mask opening) and local fiducials for fine pitch, and test points on one side at 100 mil pitch where possible. Keep MLCCs ≥3–5 mm from V-score or tab lines, and meet IPC-2221B or IEC creepage and clearance for high voltage.

### Cited Findings
- JLCPCB official capabilities (per extract), 1 oz copper: track and space 0.10/0.10 mm (4/4 mil) on 1–2 layer boards and 0.09/0.09 mm (3.5/3.5 mil) on multilayer, 3 mil only in BGA fan-outs. At 2 oz on 2-layer: 6.5/6.5 mil. Annular ring recommended 0.25 mm on 2-layer (absolute 0.18 mm) and 0.20 mm on multilayer (absolute 0.15 mm). Copper ≥0.2 mm from non-mouse-bite board edges. Edge tolerance ±0.2 mm regular / ±0.1 mm high precision. Third-party blogs quote different numbers (e.g., 5 mil). The official page wins. — [JLCPCB PCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities); [NextPCB capability comparison](https://www.nextpcb.com/blog/pcb-capabilities-comparison-jlcpcb-vs-pcbway-vs-nextpcb)
- IPC-7351 courtyard excess per side: Level A (most) ≈ 0.50 mm, Level B (nominal) 0.25 mm, Level C (least) ≈ 0.10 mm, defined per component family. The density levels are solder-fillet goals, not quality classes. — [PCB Libraries forum: courtyard excess](https://www.pcblibraries.com/forum/placement-courtyard-excess_topic3372.html); [LinkedPCBA courtyard clearance](https://www.linkedpcba.com/blog/component-courtyard-clearance-guide.html); [Ultra Librarian placement tolerance](https://www.ultralibrarian.com/2024/11/15/pcb-component-placement-tolerance-ulc/)
- Tombstoning: thermal imbalance means one end wets first and surface tension stands the part up. 0201 and 0402 are the most susceptible. Use symmetric IPC-7351 pads and thermal relief on plane-connected pads (spokes about 0.10–0.20 mm, gaps 0.20–0.30 mm for fine passives). Mirror any via within 1 mm of one pad at the opposite pad. Balance paste volume. A longer soak helps in the profile. — [JLCPCB tombstoning](https://jlcpcb.com/blog/pcb-tombstone); [AtlasPCB tombstoning prevention](https://www.atlaspcb.com/blog/pcb-tombstoning-prevention-smt/); [JLCPCB thermal relief](https://jlcpcb.com/blog/thermal-relief-pad-design)
- Fiducials: 1 mm copper target (range 1–3 mm), mask opening around 2 mm (some use 1.7 mm or 3× diameter), mask never covering it. Three global fiducials in an asymmetric L near the corners, ≥5 mm from the edge (or tied to the 7.62 mm SMEMA transport clearance). Local fiducials (two, diagonal, within 1–3 mm of the land pattern) for fine pitch. Thresholds vary: <1.0 mm, ≤0.5 mm or ≤0.4 mm pitch. Keep all fiducials the same size. — [Solutions Mfg fiducial guide](https://www.solutionsmfg.com/images/pdf/fiducial.pdf); [JLCPCB fiducials](https://jlcpcb.com/blog/pcb-fiducials); [AtlasPCB fiducials](https://www.atlaspcb.com/blog/pcb-fiducial-mark-design-placement-pick-and-place/); [OrinewPCB fiducials](https://pcbandassembly.com/blog/pcb-fiducials/)
- Test points: for bed-of-nails, 100 mil (2.54 mm) centre-to-centre is ideal and 50 mil the minimum. Pads about 0.035 in (0.9 mm) to 1.0–1.27 mm. Flying probe: pads 0.5 mm minimum / 0.75 mm recommended, spacing 60 mil minimum / 80 mil recommended. ~2.5 mm from component edges and ~0.125 in from the board edge. All on one side so a single-sided fixture works. — [Test Electronics DFT whitepaper](https://testelectronics.com/info/whitepapers/dft.php); [ALLPCB DFT handbook](https://www.allpcb.com/blog/pcb-manufacturing/optimizing-pcb-design-for-in-circuit-testing-a-design-for-testability-dft-handbook.html); [JLCPCB test points](https://jlcpcb.com/blog/pcb-test-points-and-smart-dft); [PCBSync DFT](https://pcbsync.com/dft-pcb/)
- V-score and depanel stress: keep components ≥2 mm from the V-cut centreline at minimum. Keep MLCCs 3–5 mm away (5 mm for thin 0.8 mm boards), because flex cracks can pass electrical test and fail later. Use soft-termination MLCCs near edges. Stress ranking from lowest: push-back, slit, V-groove, perforation. — [PCBGOGO V-scoring](https://www.pcbgogo.com/Article/pcb-v-scoring.html); [PCBSync V-cut](https://pcbsync.com/pcb-v-cut-scoring/); [APTPCB depanelization](https://aptpcb.com/en/blog/board-handling-and-depanelization); [ALLPCB V-scoring placement](https://www.allpcb.com/blog/pcb-knowledge/the-impact-of-v-scoring-on-pcb-component-placement-design-considerations.html)
- Panelization: rails 5–10 mm (5–8 mm typical); tooling holes 2–4 mm NPTH, asymmetric/diagonal, with copper and parts ≥2 mm from the hole edge; mouse-bite holes 0.5–1.0 mm, tabs about 2–3 mm wide every 50–90 mm; parts 1.5–2.5 mm from tabs. — [JLCPCB mouse bites](https://jlcpcb.com/blog/mouse-bite-panelization-guide); [AtlasPCB panelization](https://www.atlaspcb.com/blog/pcb-panelization-vscore-tab-routing-depaneling/); [PCBSync breakaway tabs](https://pcbsync.com/breakaway-tab-pcb/)
- High-voltage spacing (IPC-2221B Table 6-1): location codes B1 internal, B2 external uncoated (≤3050 m), B4 external with permanent polymer coating. Solder mask does not count as B4 coating. Commonly quoted rows: 31–50 V → 0.1 mm (B1) / 0.6 mm (B2) / 0.13 mm (B4); 301–500 V → 0.25 / 2.5 / 0.8 mm. Above 500 V about +0.0025 mm/V (B1) and +0.005 mm/V (B2/B4). Altitude derating applies. Creepage for safety comes from IEC 60664-1 or product standards, not IPC-2221. JLCPCB's blog table disagrees and is treated as an outlier. — [EMA clearance/creepage table](https://www.ema-eda.com/ema-resources/blog/pcb-clearance-and-creepage-distance-table/); [IndiPCB Table 6-1](https://indipcb.com/blog/ipc-2221-clearance-spacing); [AtlasPCB IPC-2221B](https://www.atlaspcb.com/blog/pcb-creepage-clearance-ipc-2221b-high-voltage-spacing/); [JLCPCB voltage clearance](https://jlcpcb.com/blog/pcb-voltage-clearance-guide)
- Polarity and orientation: align polarized parts in one direction (0°/90°). This simplifies pick-and-place and AOI, reduces errors and eases rework checks. Clear pin-1 and polarity silkscreen marks prevent misplacement. Avoid THT where possible (slower, costlier). — [Cadence DFA guidelines](https://resources.pcb.cadence.com/home/2024-dfa-guidelines-for-pcb); [Sierra Circuits DFA checklist](https://www.protoexpress.com/blog/pcb-design-for-assembly-checklist-important-checks-for-layout-engineers/); [NextPCB assembly design guide](https://www.nextpcb.com/blog/pcb-assembly-design-guide)

### Inferences

| ID | Rule | Numeric guideline | Why | Applies | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|---|
| DFM-01 | DRC minimums = fab absolute limits; router targets = fab recommended + margin | JLCPCB 1 oz: 0.10/0.10 mm (2L), 0.09/0.09 (ML); AR 0.25/0.20 mm; edge copper ≥0.2 mm (prefer ≥0.3–0.5 mm) | Yield | All | S1 if violated | KiCad board setup + custom rules; DRC | JLCPCB |
| DFM-02 | Courtyards never overlap (same side); use Level B 0.25 mm excess unless density demands it | 0.25 mm/side → ≥0.5 mm land-to-land | Placement accuracy, rework, AOI | All SMD | S2 | KiCad courtyard DRC (built in) | IPC-7351 sources |
| DFM-03 | Symmetric thermal connection of the two pads of 0201/0402/0603 passives | Same track width on both pads, or thermal relief on the plane side; vias within 1 mm mirrored | Tombstoning | Small 2-terminal SMD | S3 | For each 2-pad part: copper area connected within r = 1 mm of each pad; zone connection mode; ratio > ~2 flags | JLCPCB, AtlasPCB |
| DFM-04 | Polarized parts in a consistent orientation per board side; 0/90° only | ≤2 orientations per polarized class | Placement and AOI errors | Diodes, LEDs, tantalum/electrolytic, ICs | S4 | Histogram of rotation per class | Cadence DFA |
| DFM-05 | Single-sided SMT if it fits; if double-sided, put only light, small passives on the bottom; no THT under SMD | — | Each extra reflow pass or fixture costs money; heavy parts fall off in second reflow (general practice) | Cost-sensitive | S3 | Count bottom-side parts; mass/size heuristics | DFA sources (no direct cost source found) |
| DFM-06 | Fiducials: 3 global (L-pattern) + 2 local per fine-pitch part (≤0.5 mm pitch as default) | 1.0 mm Cu, 2.0 mm mask opening, ≥5 mm from edge, clear zone | Vision alignment | Machine assembly | S3 | Count fiducial footprints, positions, asymmetry; local fiducials near QFN/QFP/BGA with pitch ≤ threshold | Solutions Mfg, AtlasPCB |
| DFM-07 | Test point on every net needed for ICT/bring-up, on one side | ICT: ≥1.0 mm pad, 2.54 mm pitch (1.27 mm min); flying probe: ≥0.75 mm, ≥2.0 mm pitch; ≥2.5 mm from tall parts | Probe access | Production | S3 | Per-net TP coverage %; pitch and keep-out check | Test Electronics, ALLPCB |
| DFM-08 | Edge keep-outs: parts ≥ ~0.5–1 mm from routed edges (heuristic); MLCCs and BGAs ≥3–5 mm from V-score or tab lines; connectors at edges as the mechanical design dictates | V-score: ≥2 mm generic, 3–5 mm MLCC | Depanel stress cracks | Panelized | S2 (MLCC) | Distance from each footprint courtyard to Edge.Cuts / V-score lines, by part class | PCBGOGO, PCBSync |
| DFM-09 | Mounting holes: keep-out ring for screw head/washer plus tool clearance; no copper except an intentional ground ring | Ring ≥ screw-head radius + ~1 mm (heuristic; get from mechanical drawing) | Shorts, mechanical stress, cracked parts | All | S2 | Rule area per hole footprint; courtyard intersection | No source found (gap) |
| DFM-10 | High-voltage nets: clearance per IPC-2221B (B2/B4) or the safety standard; slots for creepage where needed | e.g., 301–500 V: 2.5 mm B2 | Arc-over and tracking | > ~30–50 V | S1 | Net class "HV": clearance rules in KiCad custom rules | IPC-2221B summaries |
| DFM-11 | Silkscreen: refdes legible, not on pads, consistent orientation; pin-1 and polarity marks outside the body outline | Text height ≥ ~0.8–1.0 mm, stroke ≥ ~0.15 mm (third-party, unverified) | Assembly and rework | All | S4 | KiCad silk-over-pad DRC; text size check | Third-party JLCPCB checklist (unverified) |
| DFM-12 | Height and keep-out zones from the enclosure (3D) | Per mechanical drawing | Fit | Enclosures | S1 | Footprint 3D height vs rule areas with height limits | Inference |

### Gaps
- I did not obtain PCBWay's official capability numbers, or JLCPCB's official silkscreen and via-in-pad numbers (the extract did not include them).
- No authoritative source was found for the cost premium of double-sided vs single-sided assembly, mounting-hole keep-out dimensions, or reference-designator height.
- IPC-7351 and IPC-2221B values come from secondary summaries (the standards are paywalled).

---

## 7. General placement methodology used by expert humans

### Takeaway
Experts place in order of constraint rigidity. Mechanically fixed parts go first (connectors, mounting holes, switches, LEDs, antenna and module positions, with their keep-outs). Next come the major ICs, oriented to minimize crossings and plan BGA fanout. Then the critical circuits are placed as tight, templated clusters (power stages with their hot loops, clocks and crystals, RF and matching). Decoupling goes at each IC. The rest follows signal flow and the schematic hierarchy. Placement dominates outcome; Altium cites "90% placement, 10% routing", and its own text calls the split debatable.

### Cited Findings
- Mechanical components (connectors, mounting holes, switches) go down first because the enclosure or UX sets their positions, and they are then locked. — [EMA placement best practices](https://www.ema-eda.com/ema-resources/blog/best-practices-for-pcb-component-placement-emd/)
- Next come the main functional chips (MCUs etc.), followed by auxiliary components such as decoupling caps placed close to each power pin. Group power conditioning away from sensitive RF and analog circuitry. — [EMA](https://www.ema-eda.com/ema-resources/blog/best-practices-for-pcb-component-placement-emd/); [Sierra Circuits placement rules](https://www.protoexpress.com/kb/pcb-component-placement-rules/); [Sierra Circuits placement guidelines](https://www.protoexpress.com/blog/component-placement-guidelines-pcb-design-assembly/)
- Altium states PCB design is roughly "90% placement and 10% routing" (and calls the split debatable). Good placement is critical. — [Altium BGA design article](https://resources.altium.com/p/how-to-successfully-design-a-bga); [Altium BGA pad and fanout](https://resources.altium.com/p/which-bga-pad-and-fanout-strategy-right-your-pcb)
- Organize the layout around the main SoC/BGA, which sources and sinks most signals. Prioritize high-speed connectors, memory and power ICs relative to it. Placing the BGA centrally gives equal routing access on all sides. — [PCBWay BGA guidelines](https://www.pcbway.com/blog/PCB_Design_Layout/BGA_PCB_Layout_Guidelines_Placement_Fanout_and_Routing_b8eeabdd.html)
- Plan fanout during placement by preallocating escape vias. Use dog-bone fanout for pitches ≥0.8 mm and via-in-pad (plated over) for ≤0.65 mm. Outer ball rows escape on top, inner rows on inner layers, with power and ground pins assigned first. — [AtlasPCB BGA fanout](https://www.atlaspcb.com/blog/bga-fanout-routing-strategies-dog-bone-via-in-pad/); [Altium BGA fanout](https://resources.altium.com/p/which-bga-pad-and-fanout-strategy-right-your-pcb)
- Converter-specific ordering (a micro-methodology that generalizes): IC → CIN (route immediately) → L/SW (+snubber) → COUT/VOS → small-signal → ground tie. — [TI SLYT614](https://www.ti.com/lit/an/slyt614/slyt614.pdf)

### Inferences
Recommended order of operations for an automated placer (synthesized from the above):
1. **Board and mechanical:** outline, mounting holes and their keep-outs, connectors (edge, fixed coordinates from the mechanical drawing), user-facing parts (buttons, LEDs, displays), height zones, antenna/module edge placement plus keep-out polygons. Lock all of these.
2. **Stackup and plane plan:** decide reference planes (a GND plane under all critical circuits), power distribution (which rails become planes or pours), and analog/digital/RF/power regions, partitioned so that connectors feed their own regions (I/O near connectors, Ott-style partitioning).
3. **Anchor ICs:** the main MCU/SoC/FPGA, oriented so pin groups face the peripherals they connect to (minimize ratsnest crossings). Reserve the fanout area.
4. **Critical sub-circuits as rigid templates:** switching converters (hot loop first), crystal and oscillator, RF chain and matching, ADC front-end and reference, current-sense shunts. Each template is placed as a unit near its consumer or I/O.
5. **Decoupling:** at each power pin with vias at the pads (PDN-01), before any general routing.
6. **Remaining parts by signal flow:** connector → protection/ESD (at the connector) → filter → transceiver/buffer → IC; follow the schematic hierarchy sheets as clusters.
7. **DFM pass:** orientation normalization, courtyard spacing, fiducials, test points, silkscreen.
8. **Route order:** power hot loops and RF (manual-quality, fixed) → sensitive analog/feedback → clocks and high-speed differential pairs → general signals → pours and stitching → DRC plus the custom checks in section 9.

Rule of thumb: placement quality can be scored before routing by ratsnest length, crossing count, per-region congestion and constraint-violation counts. That lets placement iterate cheaply ("placement is most of routing").

### Gaps
- Searches turned up nothing citable from Robert Feranec (FEDEVEL) or Phil's Lab on their specific placement order, so their methods are not represented here.

---

## 8. How datasheets express layout recommendations, and turning them into quantitative constraints

### Takeaway
Datasheet layout sections mix five kinds of statement: qualitative proximity ("as close as possible"), pin-specific connectivity ("connect VOS in the shortest way to VOUT at the output capacitor"; "ground the shunt cap via the VSS pin closest to ANT"), explicit numbers (keep-outs, via pitch, clearance), an ordered priority list (SLYT614's steps), and reference layout figures. An LLM must turn each into a typed constraint. Proximity words become distance or loop-area targets ranked by priority. Pin-connectivity statements become topology checks. Numbers become DRC rules. Figures become relative-placement templates.

### Cited Findings (examples of each statement type)
- Qualitative proximity: "The LDO input capacitor should be placed as close as possible to the LDOIN and PGND pins". — [Renesas AN-PM-179](https://www.renesas.com/en/document/apn/da9080-pcb-layout-recommendations)
- Relative proximity priority: "Place inductor close to IC, no need to be as close as input capacitor". — [Rohm buck layout](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf)
- Pin-and-point connectivity: "connect the VOS pin in the shortest way to VOUT at the output capacitor". AGND and PGND to the exposed pad and system ground is "mandatory". — [TI TPS62130 datasheet](https://www.ti.com/lit/ds/symlink/tps62130.pdf)
- Pin-specific grounding: "the shunt capacitor closest to the radio should be grounded via the VSS pin closest to the ANT pin". — [Nordic DevZone nRF52 guidelines](https://devzone.nordicsemi.com/guides/hardware-design-test-and-measuring/b/nrf5x/posts/general-pcb-design-guidelines-for-nrf52-series)
- Explicit numeric: ≥15 mm antenna clearance (Espressif); ground vias ≤0.5 mm from the coplanar ground edge at ≤2 mm pitch (u-blox); about one via per ampere (TI SLVA773). — [Espressif](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html); [u-blox NORA-B2 SIM](https://content.u-blox.com/sites/default/files/documents/NORA-B2-u-connectXpress_SIM_UBXDOC-465451970-3906.pdf); [TI SLVA773](https://www.ti.com/lit/an/slva773/slva773.pdf)
- Ordered procedure: SLYT614's five steps (CIN → L/snubber → COUT/VOS → small signal → ground). — [TI SLYT614](https://www.ti.com/lit/an/slyt614/slyt614.pdf)
- Reference design deference: Nordic says to use its reference design for exact component values and layout, because the matching topology differs between QFN and WLCSP packages. — [Nordic DevZone nRF52 guidelines](https://devzone.nordicsemi.com/guides/hardware-design-test-and-measuring/b/nrf5x/posts/general-pcb-design-guidelines-for-nrf52-series)

### Inferences
Suggested translation table (phrase → constraint type → default parameters; defaults are heuristics to calibrate):

| Datasheet phrase pattern | Constraint type | Default quantification | Notes |
|---|---|---|---|
| "C_x as close as possible to pin(s) P" (power-stage cap) | `proximity(part, pins, max_gap)` + `same_layer` + `max_vias=0` + priority rank 1 | Pad-edge gap ≤ 0.5 mm (0402/0603), ≤ 1.0 mm (0805+) | Also emit a `loop_area(part, pins) ≤ A_max` metric for scoring |
| "close to IC" / "near" (secondary) | `proximity(max_gap)` with lower priority | ≤ 3–5 mm | Rohm: inductor less tight than CIN |
| "Connect X to Y at Z" (Kelvin/sense) | `connect_at(net, pad_of_part)` + `separate_from(net, high_current_net)` | Sense trace must leave from the Z pad, not share copper with the power path before Z | TPS62130 VOS |
| "Shortest path" / "short and wide" | `max_length` + `min_width` | Length ≤ 5 mm (heuristic); width from IPC current | — |
| "Keep away from SW / inductor / noisy" | `keepout(net_class, aggressor, distance, layers=all)` | ≥ 1–2 mm clearance; no overlap with aggressor courtyard on any layer | — |
| "Do not route under X" | Rule area over the X courtyard: `disallow tracks/vias` for listed classes, on the listed or all layers | — | KiCad rule areas support this (verify syntax) |
| "Ground via near pad" / "via fence" | `via_near(pad, net=GND, max_dist)` / `via_fence(net, pitch, offset)` | 0.5 mm / λ/20 or 2 mm | — |
| "Mandatory" / "must" | Hard constraint (S1) | — | Treat "should"/"recommended" as S2–S3 |
| Numeric keep-out/clearance | DRC rule as written | — | Store the units, layer and condition |
| Layout example figure | `relative_placement_template` (positions/rotations relative to the IC) | Extract with a vision model, normalized to pin-1 orientation | Use as an initial placement seed |
| Ordered steps | `placement_priority` ordering | — | Place and route in that order |

### Gaps
- No published taxonomy of datasheet layout-guideline language was found. The table above is my synthesis from the examples cited.

---

## 9. Implications for an LLM-driven KiCad placer/router

### Takeaway
The highest-value automation is recognizing circuit roles (CIN_HF, SW, L, COUT, FB divider, BOOT, RSENSE, crystal, RF match, ADC AGND/DGND) from the netlist plus pin names and datasheet text, then instantiating per-topology placement templates and typed constraints with severities. Every constraint gets a geometric checker, such as loop area, adjacency, keep-out intersection or via pitch. The LLM's job is extraction and templating; the checks must be deterministic code over the KiCad board model.

### Cited Findings
- The rules that most need automation are the ones the sources rank first: hot-loop minimization and CIN-first placement ([TI SLYT614](https://www.ti.com/lit/an/slyt614/slyt614.pdf); [ADI AN-139](https://www.analog.com/en/resources/app-notes/an-139.html)), feedback isolation and Kelvin sensing ([TI TPS62130 datasheet](https://www.ti.com/lit/ds/symlink/tps62130.pdf)), antenna keep-outs ([Espressif](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html)), single-plane partitioning ([Ott](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html)) and fab minimums ([JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities)).

### Inferences

**A. Auto-identifying a switching converter and its hot loop from the netlist and datasheet**
1. *Candidate detection:* any IC with a pin named or described as one of {SW, LX, PH, SW1/SW2, LX1..} and also {VIN, PVIN, VCC} and {PGND, GND, EP}. Or a discrete half-bridge: two FETs sharing a node that also connects to an inductor. Confirm with datasheet keywords ("step-down", "buck", "boost", "inverting", "flyback").
2. *Topology classification from inductor connectivity:*
   - L between the SW net and the regulated output net, and a FB divider from that output → **buck**.
   - L between an input-rail net and SW, with a diode or sync FET from SW to the output → **boost**.
   - L from SW to GND and output negative → **inverting buck-boost**.
   - Transformer (≥2 coupled windings) with a FET on the primary → **flyback/forward**. Two SW nodes with one L between them → **4-switch buck-boost**.
3. *Role assignment:*
   - CIN_HF = the smallest-package capacitor directly between the input net and PGND (ties: lowest value or smallest package).
   - CIN_BULK = the other caps on the same pair.
   - COUT = caps between VOUT and GND.
   - FB_TOP/FB_BOT = resistors on the FB pin net.
   - C_BOOT = cap between BOOT/BST/CB and SW.
   - SNUB = series RC from SW to GND.
   - RSENSE = low-ohm resistor (≤ 100 mΩ) in a power path whose ends go to CS+/CS− or SENSE pins.
   - AGND/PGND pins identified by name.
4. *Hot loop set:* buck = {CIN_HF, IC.VIN pins, IC.PGND pins} (or {CIN_HF, Q_HS, Q_LS/D}); boost = {COUT_HF, rectifier, Q_LS / IC.SW+PGND}; flyback = primary {CIN, T.pri, Q, RSENSE}, clamp {T.pri, D_clamp, C/R_clamp}, secondary {T.sec, D_rect, COUT}. Use the topology table in section 1.
5. *Datasheet augmentation:* retrieve the "Layout Guidelines" and "Layout Example" sections. Parse the statements with the section 8 table into constraint objects. Extract the example-layout figure as a relative template. Datasheet constraints override generic defaults.

**B. Constraint schema to generate (example):**
```yaml
- id: U3.hotloop
  type: loop_area
  members: [C12.pad1, U3.PVIN, U3.PGND, C12.pad2]   # ordered
  max_mm2: 15          # default; tighten per package
  same_layer: true
  max_vias: 0
  severity: S1
  source: "TI SLYT614 step 1; ADI AN-139"
- id: U3.l_adjacent
  type: proximity
  a: L2.pad_dot        # start-of-winding pad
  b: U3.SW
  max_gap_mm: 2.0
  require_net_match: {L2.pad_dot: SW}
  severity: S2
- id: U3.fb_kelvin
  type: connect_at
  net: VOUT_SENSE
  at_pad: C20.pad1     # output capacitor
  forbid_shared_copper_with: [VOUT_POWER_PATH]
  severity: S1
- id: U3.fb_keepout
  type: keepout
  victim_netclass: SENSITIVE   # FB, COMP, SS, RT
  aggressors: [net:SW, courtyard:L2]
  clearance_mm: 1.0
  layers: all
  severity: S1
- id: U3.L2_plane
  type: solid_reference
  region: hull(U3.hotloop.members) + 1mm
  layer: In1.Cu
  net: GND
  severity: S2
- id: U3.ep_vias
  type: via_array
  region: U3.EP
  drill_mm: 0.3
  pitch_mm: [1.0, 1.2]
  fill: plugged_or_tented
  severity: S2
```

**C. Checks to build (deterministic, over the pcbnew Python API):**
- *Loop area:* the polygon area of ordered pad centroids, plus a track-path-aware estimate (shoelace on the actual routed path through pads and tracks; include via-layer excursions as a penalty, e.g., area += via_count × board-thickness-based term). Report nH with a rough estimate: L ≈ μ0·h·length/width for a loop over a plane, or plain area ranking.
- *Adjacency and proximity:* pad-edge-to-pad-edge distance; same-side test; via count on the shortest copper path between two pads (graph search over the track and via graph).
- *Reference-plane integrity:* rasterize zones on the adjacent layer under a region or along each critical track; flag voids, slots and foreign nets. Detect tracks crossing zone boundaries or splits (Ott).
- *Coupling:* parallel-run length and minimum distance between victim and aggressor nets, layer-aware (the same layer and adjacent layers count).
- *Keep-out compliance:* intersection of copper on all layers with the antenna and module keep-out polygons; under-inductor keep-outs.
- *Via fence and stitching:* along an RF net centreline, max spacing between GND vias within offset ≤ X mm; pour stitching max gap ≤ λ/20.
- *Thermal:* EP via count and pitch; estimated power per part (from rail currents and topology) vs connected copper area; pairwise distances between hot and sensitive classes.
- *DFM:* courtyard overlaps (KiCad built-in), tombstone asymmetry metric (connected copper within 1 mm of each pad), rotation histograms for polarized classes, fiducial count and placement, test-point coverage, distance to edges and V-score lines by part class, HV clearance by net class.
- *PDN:* for each power pin, the nearest decoupling cap distance and via distance; DC-bias-derated capacitance totals vs Z_target; ferrite-bead resonance vs f_sw.

**D. KiCad encoding notes (verify syntax against current KiCad docs before use):**
- Net classes per role: `PWR_HOT`, `SW`, `SENSITIVE` (FB/COMP/RT/SS/REF/crystal), `RF50`, `HV`, `ANALOG`, `DIGITAL`. Generate widths and clearances from the IPC formula and fab limits.
- Custom DRC rules (`.kicad_dru`) with conditions on `A.NetClass` / `B.NetClass`, `A.insideArea('...')` and layer. For example, clearance between `SENSITIVE` and `SW` ≥ 1 mm. Rule areas from module and antenna keep-outs that disallow tracks, vias and zones on all layers. Courtyard-clearance and edge-clearance rules by part class (MLCC near V-score).
- Geometric metrics that KiCad DRC cannot express (loop area, Kelvin tap point, solid-reference coverage, via-fence pitch, tombstone symmetry) should be custom Python checks that emit KiCad-style marker reports. The LLM can then read them and repair the board iteratively.

**E. Placement strategy for the LLM agent:**
- Use *template-first, then global*. Build each critical block (buck, LDO, crystal, RF match, ADC front-end, shunt) as a locally optimized rigid macro, using datasheet example layouts where available. Then place the macros plus the remaining parts with a global placer whose objective = ratsnest length + crossing count + violation penalties weighted by severity (S1 ≫ S2 ≫ S3).
- *Priority ordering inside blocks* follows the datasheet steps (SLYT614: CIN, then L, COUT, FB, AGND tie).
- *Region partitioning:* assign each schematic block to a region (power, analog, digital, RF, HV). Penalize cross-region nets except at designated boundary parts (ADCs, isolators, connectors). Keep switcher hot loops ≥ X mm from RF and analog regions.
- *Route critical nets first and freeze them:* hot loops, SW, RF, Kelvin sense, crystal. Then general routing. Then pours, stitching and fences. Then re-run all checks.
- *Treat low-authority numeric rules as soft objectives*, not hard DRC (e.g., 20 mm RF-to-SMPS separation, 2 cm²/W). Keep the provenance (source URL, authority level) on every constraint so humans can audit and override.

**F. Context-dependence flags to encode** (so the system doesn't over-apply rules):
- 90° corners: ignore below ~1 GHz. Miter or arc only on RF and multi-GHz nets.
- Split ground: never by default. Only when a datasheet mandates it, and then with a single bridge and crossings over the bridge.
- Decoupling "smallest closest": implement as "lowest mounting inductance closest".
- Copper under inductors: follow the datasheet. Default: top-layer void under unshielded inductors, inner GND solid.
- Ferrite beads: add only on explicit requirement, and always run the resonance check.

### Gaps
- No published system or paper was found in this session that auto-extracts hot loops from netlists. The algorithm above is a proposal and needs validation on real designs (e.g., a corpus of open-source KiCad boards with known regulators).
- I could not consult KiCad's custom-rules documentation here (the network was blocked). The rule syntax mentioned must be checked against the installed KiCad version.
- The default numeric thresholds (pad gaps, loop-area caps, keep-out distances) are uncalibrated heuristics. They should be tuned against reference layouts from TI, ADI and Espressif evaluation boards.
