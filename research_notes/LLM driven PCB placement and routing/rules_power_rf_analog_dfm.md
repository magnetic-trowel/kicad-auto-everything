# PCB Placement and Routing Rules: Power Conversion, PDN and Decoupling, RF, Analog and Mixed-Signal, Thermal, DFM/DFA, and Placement Method

How this was researched, and its limits (two passes):
- **Pass 1 (sections 1–8):** WebFetch could not resolve DNS, and the egress proxy blocked ti.com, analog.com and most vendor hosts. Every finding in sections 1–8 therefore came from extended web-search extracts of the cited documents. Treat all of it as **[S]** unless a bullet is explicitly re-tagged **[P]**.
- **Pass 2 (sections 9–19 and additions marked [P]):** with full access, I downloaded primary PDFs and web pages with curl and read the relevant sections as text (pdftotext). WebFetch still failed on DNS. analog.com redirects to a CDN host (www-cce.cldnet.analog.com) where the proxy tunnel closed mid-exchange on every attempt, so ADI/LT app notes were read from mirrors: AN-136, AN-139, AN47 (MIT copy). This pass ended when the session's web-search budget ran out (200 searches across all agents). Topics that would have needed more searching are listed as gaps.
- **Provenance tags:**
  - **[P]** = I read this in the primary document itself (datasheet, app note, standard summary by the standard's user, or the author's own page) during pass 2.
  - **[P-sec]** = I read it in full, but the page is a secondary account of someone else's material (for example a course review).
  - **[S]** = search-engine extract only; not read in the source.
- Where only a vendor blog backs a number, it is also marked "(low authority)". Rules I derived from circuit physics rather than from a source are kept in the "Inferences" subsections.
- A separate agent is verifying the numbers in sections 1–8. Pass 2 therefore concentrated on circuit classes and topics not yet covered: isolation/HV/mains, offline flyback, motor drivers, LED drivers, chargers/BMS, high-current/busbars, precision sensor front-ends, audio, PDN methodology, thermal methodology, and practitioner material (Feranec, Phil's Lab, Pease, Williams).

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
- **[P] AN-136 (Henry J. Zhang, June 2012), read from a mirror of the LT PDF in pass 2:**
  - Place DC ground or DC voltage layers between the high-current power-component layer and the small-signal layer, and "always have a ground layer next to the outside power stage layer". Do not segment ground or DC planes. Use thick copper on the external high-current layers.
  - Place the power stage first; the small-signal control circuitry follows.
  - C_HF is a 0.1–10 µF X5R/X7R ceramic with very low ESL.
  - Put power components on the same side and power traces on the same layer. If a power trace must change layers, do it in a continuous-current path (not the hot loop), using multiple vias.
  - Boost: C_HF goes on the output side, close to the MOSFET and the diode.
  - Minimize SW copper area, but keep enough for current and heatsinking. "It is usually preferred to have a ground copper area placed underneath this SW node to provide additional shielding."
  - Do not use thermal-relief land patterns or thermal-relief vias for power components; they raise interconnect impedance and weaken low-ESR caps. Keep a decoupling cap's +/− via pair as close together as possible.
  - Locate the controller near VOUT+ (buck) or VIN+ (boost), away from the hot loop, shielded by ground if forced close. Connect controller decoupling caps directly to the pins without vias.
  - One SGND–PGND connection, made just under the controller IC (or at a clean PGND point). Solder the exposed GND pad with multiple vias.
  - Current-sense: signals are typically <100 mV. Route SENSE+/SENSE− in parallel with minimum spacing (Kelvin), with filter R/C as close to the IC pins as possible. For DCR sensing, R goes near the inductor and C near the IC. A sense-return via must not contact an internal VOUT+ layer.
  — [AN-136 (mirror of LT PDF)](https://docs.ampnuts.ru/analog.com.datasheet/ltc3729l-6/related_data/an136f.pdf); [ADI AN-136 page](https://www.analog.com/en/resources/app-notes/an-136.html)
- **[P] AN-139 (Christian Kueck, Oct 2012), measured loop inductance vs a plane under the loop.** Table 1: 10 × 10 cm rectangular loop at 27 MHz.

  | Configuration | Plane distance d | L | Factor vs 0.12 mm plane |
  |---|---|---|---|
  | Single-layer open loop | — | 187 nH | 14.4× |
  | Inner copper short-circuit loop | — | 141 nH | 10.85× |
  | Solid plate | 1.5 mm | 42 nH | 3.23× |
  | Rectangular loop, no overlap | 1.5 mm | 53 nH | 4.08× |
  | Thin plane | 0.5 mm | 23 nH | 1.77× |
  | Thin plane | 0.27 mm | 21 nH | 1.61× |
  | Paper-thin insulation | 0.12 mm | 13 nH | 1.0× |

  - "A solid plane on the next layer in a multilayer board (four layers or more) will have over 3× less inductance than a normal 1.5mm 2-layer board with a solid bottom plane, and over 14× less over a single-layer board."
  - The mechanism is eddy currents in the plane, which mirror and cancel the hot-loop field, more effectively the closer the plane is.
  - In AN-139's buck-boost example, RF energy in the input-cap hot loop was >20 dB higher than in the INTVCC decoupling loop. That makes the INTVCC/driver decoupling loop the second priority, shielded by a solid plane on the next layer.
  — [AN-139 (mirror of LT PDF)](https://theengineer.markallengroup.com/production/content/uploads/2015/01/an139f.pdf)
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
- AN-136 and AN-139 were read from mirrors in pass 2 (see the [P] bullets above). I did not re-read TI SLYT614 steps 2–5; a separate verification agent covers that.
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
- **[P]** Archambeault, "PCB Power Decoupling Myths Debunked" (IEEE EMC chapter, Oct 2012). His "conventional wisdom" slide lists five beliefs the talk tests: you need a variety of values; many caps of one value are better than many values; place caps as close to ICs as possible; location does not matter; spread caps over the entire board. His title slide answers "It's really the inductance that matters!" Findings:
  - Capacitance values should be as large as possible within the package size.
  - In most cases the IC takes charge from between the planes, and the caps replenish that charge.
  - Caps provide charge better when spread out.
  - If caps sit near each other, alternate their power/ground pin orientation. The worst case is caps close together with all pins in the same direction.
  - A plane pair deep in the stackup has higher effective inductance.
  - Inductance rises rapidly as plane width decreases, so avoid long thin power/ground structures.
  - In his plane-recharge study with a thick (35 mil) dielectric, "Location does matter!"
  — [Archambeault slides](https://ewh.ieee.org/r3/enc/emcs/archive/2012-10-10b_DecouplingMyths.pdf)
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
- **[P] Ott, primary page (re-read in pass 2), with details the snippet missed:**
  - He gives a resolution table for a 1 V reference: 8 bit = 4 mV, 10 bit = 1 mV, 12 bit = 240 µV, 14 bit = 60 µV, 16 bit = 15 µV, 20 bit = 1 µV, 24 bit = 60 nV. Scale by V_ref. Keep analog ground-plane noise below the smallest analog signal of concern.
  - A single solid, partitioned plane is "usually adequate" for 8–12-bit converters.
  - For ≥14-bit converters, divide the board into isolated analog and digital ground regions, each solidly connected to the digital ground plane under each A/D converter. Even then the plane is not split, and no trace on any layer may cross the isolating slots.
  - Proposed check: lay out the split with jumpers or 0 Ω links every 1/2 inch, and compare performance with them open and closed.
  - Datasheet "AGND+DGND to the analog plane" advice raises an unanswered question: where does the digital decoupling cap ground go? His answer is to use one plane from the start.
  — [Ott tech tip (primary)](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html)
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
- **[P]** For the primary-source thermal methodology (TI SNVA419, SPRA953, SLMA002, SLVA959), including a 261 °C/W per-via figure for a 12-mil via with 0.5 oz plating, a 1 mm via-array pitch, and board-area rules, see section 18. — [TI SNVA419](https://www.ti.com/lit/pdf/snva419)
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
- **[P] JLCPCB capabilities page (read 2026-10-20). Additions to the [S] bullet below:**
  - Track and space by copper weight:
    - 2 oz: 0.16/0.16 mm (2-layer), 0.15/0.15 mm (multilayer).
    - 2.5 oz: 0.20/0.20 mm. 3.5 oz: 0.25/0.25 mm. 4.5 oz: 0.30/0.30 mm (2-layer only).
    - Available weights: 2-layer 1/2/2.5/3.5/4.5 oz outer; multilayer 1/2 oz outer; inner layers 0.5 oz by default.
  - Track width tolerance ±20%.
  - PTH annular ring at 2 oz ≥0.254 mm. NPTH pad ring recommended ≥0.45 mm.
  - Pad-to-track clearance 0.1 mm (1 oz). SMD pad spacing ≥0.10 mm (1 oz, most mask colours) or 0.20 mm (2 oz).
  - Pad-to-silkscreen ≥0.15 mm.
  - Copper to routed edge ≥0.2 mm, and to V-cut edge ≥0.4 mm. V-cut edge tolerance ±0.4 mm (board ≥0.6 mm). Minimum spacing between two V-cuts 2 mm (3 mm recommended).
  - Inner-layer via-hole-to-copper clearance 0.2 mm; inner PTH-hole-to-copper 0.3 mm.
  - Vias in BGA pads require filled and plated-over vias.
  — [JLCPCB PCB capabilities (primary)](https://jlcpcb.com/capabilities/pcb-capabilities)
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
- Pass 1 found nothing citable from Robert Feranec (FEDEVEL) or Phil's Lab. Pass 2 found some, plus Pease and Williams material; see section 19.

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

## 9. Isolation barriers, creepage and clearance (IEC 60664-1, IEC 62368-1, IPC-2221B), and high-voltage / mains safety layout

### Takeaway
Safety spacing is not a single DRC number. It is a lookup chain:
- Insulation grade (functional, basic, reinforced) comes from the end-product standard.
- **Creepage** = f(working voltage RMS, pollution degree, material group by CTI). Double it for reinforced insulation.
- **Clearance** = f(rated impulse voltage from mains voltage and overvoltage category, pollution degree, altitude). For reinforced insulation, use one impulse step higher (IEC 60664-1) or the reinforced column of IEC 62368-1 Table 10.

IPC-2221B and IPC-9592B cover functional spacing only, not user safety. Slots extend creepage only if they are wide enough (≥1.0 mm at pollution degree 2). Keep the area under isolators and transformers free of copper on all layers. When the spacing cannot be met, the remedies are coating, slots, or a production hi-pot test (for functional isolation).

### Cited Findings
- **[P] Method (TI SLUP419, "Demystifying Clearance and Creepage Distance for High-Voltage End Equipment", Power Supply Design Seminar, rev. March 2024).**
  - *Creepage:* determine the working voltage, the insulating material's group and the environment's pollution degree. Decide basic vs reinforced from IEC 60950-1 Figure 2H. Double the table value for reinforced.
  - *Tables by end equipment:* IEC 60664-1 Table F.4 (general purpose); IEC 62368-1 Table 17 (audio/video/ICT); IEC 61800-5-1 Table 10 (motor drives); IEC 62109-1 Table 14 (solar).
  - *Clearance:* find the rated impulse voltage from IEC 60664-1 Table F.1 (mains voltage × overvoltage category), then the clearance from Table F.2 (or IEC 62368-1 Table 10, which gives both basic and reinforced). For reinforced isolation under other standards, use the impulse voltage one step up.
  - *Altitude:* above 2000 m, multiply clearance by the IEC 60664-1 Table A.2 factor.
  - *Scope:* PCB-spacing standards (IPC-2221B; the stricter IPC-9592B) "address proper or functional operation only and do not address user safety".
  - *Coating:* a coated PCB can lower the pollution degree (IEC 62109-1 via IEC 60664-3), or IEC 62368-1 Table G.13 can be used for coated boards.
  — [TI SLUP419](https://www.ti.com/lit/pdf/slup419)
- **[P] SLUP419 lookup tables (subsets it reproduces):**
  - **Material groups by CTI:** I ≥600 V; II 400–600; IIIa 175–400; IIIb 100–175. All TI isolation products are group I. Typical FR-4 is group III/IIIa (see also the [S] note in section 6).
  - **Pollution degrees:** PD1 = no pollution or only dry, nonconductive pollution (coated assemblies). PD2 = occasional temporary conduction from condensation (labs, offices, server/telecom enclosures). PD3 = conductive pollution, or nonconductive pollution made conductive by expected condensation (industrial). PD4 = continuous conductivity (outdoor).
  - **Overvoltage categories:** I (protected circuits) through IV (origin of installation).
  - **IEC 60664-1 F.4 creepage subset (mm):**

    | V_RMS working | PD1, any group | PD2 group I | PD2 group II | PD2 group III |
    |---|---|---|---|---|
    | 63 | 0.2 | 0.63 | 0.9 | 1.25 |
    | 400 | 1.0 | 2.0 | 2.8 | 4.0 |
    | 800 | 2.4 | 4.0 | 5.6 | 8.0 |
    | 1000 | 3.2 | 5.0 | 7.1 | 10.0 |

  - **F.1 rated impulse (V_peak) by line-to-neutral voltage, OVC I/II/III/IV:**
    - ≤50 V: 330 / 500 / 800 / 1500
    - ≤150 V (US 120 V): 800 / 1500 / 2500 / 4000
    - ≤300 V (EU/China 230 V): 1500 / 2500 / 4000 / 6000
    - ≤600 V: 2500 / 4000 / 6000 / 8000
  - **F.2 clearance by impulse voltage** (IEC 62368-1 Table 10 values in parentheses):
    - 0.5 kV: 0.04 (PD1) / 0.2 (PD2) / 0.8 mm (PD3)
    - 1.5 kV: 0.5 (0.76) mm at PD1–2, 0.8 mm at PD3
    - 2.5 kV: 1.5 (1.8) mm
    - 4.0 kV: 3.0 (3.8) mm
    - 6.0 kV: 5.5 (7.9) mm
  - **Worked example (telecom AC/DC front end, 265 V, OVC II, PD2, 5000 m, reinforced):** creepage 4 / 5.6 / 8 mm for material group I / II / III (2/2.8/4 mm × 2, IEC 62368-1 Table 17). Clearance 3.6 mm × 1.48 altitude factor = 5.33 mm (IEC 62368-1 Table 10).
  — [TI SLUP419](https://www.ti.com/lit/pdf/slup419)
- **[P] SLUP419, exceptions when spacing cannot be met:**
  - A slot (groove) increases creepage but not clearance. Minimum slot width: 0.25 mm (PD1), 1.0 mm (PD2), 1.5 mm (PD3).
  - Conformal coating helps when clearance cannot be met.
  - For functional isolation only, a routine hi-pot test can substitute. The test voltage is typically 2 × V_working + 1000 V (example: 265 VAC → 1530 V, hence the common 1.5 kV test).
  - A common trap is a group-I IC package (4 mm creepage) on a group-IIIa PCB (8 mm needed). A slot is the usual fix.
  — [TI SLUP419](https://www.ti.com/lit/pdf/slup419)
- **[P] TI Digital Isolator Design Guide (SLLA284G, 2023):**
  - Use ≥4 layers for a low-EMI design, stacked high-speed signal / ground / power / low-speed signal.
  - On all layers, keep the space under the isolator free of traces, vias and pads to maintain creepage.
  - A groove >1 mm wide counts if existing creepage + groove width + 2 × groove depth ≥ the required creepage, and the groove must not weaken the board mechanically.
  - A higher package CTI permits a smaller package for the same working voltage.
  — [TI SLLA284](https://www.ti.com/lit/pdf/slla284)
- **[P] Power Integrations AN-72 (InnoSwitch3 design guide, Nov 2025), safety layout for offline converters:**
  - Keep >8 mm between primary and secondary circuits, especially under the InSOP package and the transformer. Do not place spark gaps near or across the IC package, and route no traces beneath the IC.
  - Spark gaps go from the secondary terminals (output return and positive) to one AC input after the fuse. AN-72 quotes 6.4 mm (5.5 mm acceptable, depending on customer requirement) in the layout section, and "at least 5.4 mm" in the ESD section. The two figures in the same document disagree.
  - Put a spark gap across the common-mode choke.
  - A heat spreader across the barrier needs a 0.4 mm mylar pad for reinforced isolation.
  — [PI AN-72](https://www.power.com/sites/default/files/documents/an-72_innoswitch3_family_design_guide_20251107.pdf)
- **[P]** The TI BQ76952 reference layout includes PCB spark gaps (reference prefix E) fabricated in copper with no component installed. — [TI BQ76952 datasheet §18](https://www.ti.com/lit/ds/symlink/bq76952.pdf)
- [S] Coated PCBs can use IEC 62368-1 Table G.13. One calculator notes that reinforced creepage is double basic. — [smps.us creepage calculator](https://pcbdesign.smps.us/creepage.html)

### Inferences

| ID | Rule | Numeric guideline | Why | Applies | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|---|
| ISO-01 | Every net gets a voltage class and every net pair an insulation grade (functional, basic, reinforced) from the schematic: mains, primary bulk, secondary SELV, earthed chassis | Store V_working(RMS), V_peak, OVC, PD, MG, altitude | Spacing is a function of these, not of the net name | Any design >~30 V or mains-connected | S1 | Missing classification = error | SLUP419 |
| ISO-02 | Creepage constraint per net-pair = table(V_RMS, PD, MG) × (2 if reinforced) | e.g., 400 V working, PD2, MG III: basic 4.0 mm, reinforced 8.0 mm (SLUP419 subset). The 250 V row (~2.5 mm basic for MG III, from my memory of F.4) is not in the TI subset; verify it in the standard | Surface tracking | Isolated designs | S1 | **Surface-path** distance between copper of the two classes, routed around slots narrower than the PD minimum. KiCad 9+ reportedly has a creepage DRC constraint (verify) | SLUP419, IEC 60664-1 |
| ISO-03 | Clearance constraint = F.2 / IEC 62368-1 Table 10 at the impulse voltage (one step higher for reinforced) × altitude factor | 230 V OVC II → 2.5 kV → 1.5 mm basic (1.8 mm under 62368); reinforced 4 kV → 3.0 mm (3.8 mm) | Arc-over in air | Isolated designs | S1 | 3-D straight-line copper-to-copper distance, including across slots and component bodies | SLUP419 |
| ISO-04 | Barrier keep-out: no copper, vias or pads on **any** layer in the projected footprint of isolators, optos, and the primary-secondary span of transformers; the slot centreline lies under the barrier | Keep-out width ≥ required creepage | Inner-layer copper bridges the barrier; through-insulation | Isolators, flyback transformers | S1 | Rule area per isolating footprint (all layers); DRC | SLLA284, PI AN-72 |
| ISO-05 | Slots are valid only if wider than the PD minimum | ≥1.0 mm at PD2 (0.25 PD1, 1.5 PD3) | Narrow slots fill with contamination | When slots are used | S1 | Edge.Cuts slot width check | SLUP419 |
| ISO-06 | Spark gaps as copper features (no part), from secondary output to AC line after the fuse, and across the CM choke | ~5.4–6.4 mm per PI (device-specific) | ESD / surge path away from the controller | Offline adapters | S2 | Footprint presence + gap measurement | PI AN-72 |
| ISO-07 | Y capacitor routed from the primary bulk + (or AC after the fuse) to the secondary output + or return; never via controller ground | — | Routes common-mode surge current away from the IC | Offline flyback | S2 | Net connectivity of the Y-cap pins | PI AN-72 |
| ISO-08 | Fuse first at AC entry; everything downstream of the fuse is "fused primary"; line-to-line spacing upstream of the fuse also meets the table | — | Fault energy | Mains input | S1 | Topology: the fuse must be the first series element from the AC connector | General practice (no primary source read in this pass) |

### Gaps
- I did not read IEC 60664-1, IEC 62368-1 or IEC 61010-1 themselves (they are paywalled). All values above come from TI's reproduction of table subsets. Table 17 (62368 creepage) values for other voltages, the Table G.13 coated values, and ES1/ES2/ES3 energy-source class boundaries still need the standard.
- I could not research mains input-filter layout (X/Y-cap and CM-choke placement, keeping filter input and output apart) or MOV and fuse placement from a primary source before the search budget ran out. Only AN-72's points above are covered.
- I did not verify whether KiCad's DRC implements surface-path creepage (as opposed to clearance) in the installed version.

---

## 10. Isolated and offline flyback converters (layout detail beyond section 1)

### Takeaway
An offline flyback has at least four critical loops:
1. Primary: bulk cap → primary winding → switch → sense resistor.
2. Clamp: primary winding → clamp parts.
3. Secondary: secondary winding → rectifier or SR FET → COUT.
4. Bias winding loop.

Each must be tight, and no loop may sit inside another. The drain node is the dominant noise source, so keep it small and away from feedback. Use single-point (star) grounds on each side. Take feedback before any post-filter inductor. The Y-cap and spark-gap paths divert surge current away from the controller.

### Cited Findings
- **[P] PI AN-72 "Recommendations for Circuit Board Layout" (InnoSwitch3, Nov 2025):**
  - Single-point ground from the input filter capacitor to the copper on the SOURCE pin.
  - The PRIMARY BYPASS, SECONDARY BYPASS and FEEDBACK decoupling caps sit directly adjacent to their pins.
  - The feedback and monitoring resistors (R_LS, R_BP, R_FB upper/lower, R_IS) go as close as possible to the IC pins, with short traces.
  - Keep high-dV/dt and di/dt circuits as small as possible. The primary loop (input filter cap, transformer primary, IC D-S) "must be tight and small as possible".
  - Clamp (RCD, or a ~200 V Zener + diode): minimize the loop between the clamp components, the transformer and the IC. Place the clamp parts physically away from the PRIMARY BYPASS pin, with minimal trace width and length.
  - Secondary loop (N_S, C_OUT, SR FET) tight. Give the SR FET terminals copper for heatsinking. Keep the SR FET source to IC GROUND distance short.
  - Feedback (R_FB upper) and the VOUT pin connect **before** the post-filter inductor. The post-filter L/C sit as close as possible to the output terminals.
  - Secondary star ground at the R_IS node, with separate ground traces for the GND pin, C_OUT and feedback parts. On the primary, the bias-supply and SOURCE ground traces are separated and joined at a single point.
  - "No loop area should be placed inside another loop."
  - With an input π filter, place the filter inductor between the **negative** terminals of the input caps.
  - Keep quiet traces (Y-cap, feedback return) away from noisy nodes: drain, "underneath transformer belly", the switching side of any winding, and the output rectifier.
  - No signal trace may share a path with AC switching currents (for example output caps). Star-connect at the capacitor pad.
  - Keep the drain trace's surface area and length minimal (RFI).
  — [PI AN-72](https://www.power.com/sites/default/files/documents/an-72_innoswitch3_family_design_guide_20251107.pdf)
- [S] Flyback ringing on the secondary rectifier can be more destructive than the primary waveforms. A secondary RC snubber may be needed. — [ADI Flyback Snubber Design](https://ez.analog.com/cfs-file/__key/telligent-evolution-components-attachments/00-330-01-00-00-06-34-74/FlybackSnubberDesign.pdf)

### Inferences

| ID | Rule | Numeric guideline | Why | Applies | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|---|
| FLY-01 | Identify loops from the netlist: primary {C_bulk, T.pri, Q (or IC D/S), R_sense}; clamp {T.pri, D_clamp, C/R_clamp or TVS}; secondary {T.sec, D/SR, C_out}; bias {T.aux, D_bias, C_bias} | Loop-area objective for each; primary ranked highest on the primary side, secondary on the secondary side | High di/dt; dV/dt at drain | Flyback/forward | S1 | Ordered-pad polygon area per loop | PI AN-72 |
| FLY-02 | Loops must not nest: no loop polygon contains another loop's pads | — | Mutual coupling, ground-impedance noise | All isolated | S2 | Polygon containment test | PI AN-72 |
| FLY-03 | Drain-node copper minimal; no quiet nets on any layer under the transformer "belly", drain, or switching winding pins | Keep-out = transformer body + drain copper hull + ~1–2 mm (heuristic) | Capacitive and magnetic coupling | Offline | S2 | Rule area from footprint; parallel-run checks | PI AN-72 |
| FLY-04 | Feedback tap before the post-filter L; the post filter sits at the output connector | — | Control-loop stability; filter effectiveness | Post-filtered outputs | S1 | FB divider top connects to the net between C_out and L_post | PI AN-72 |
| FLY-05 | Star ground nodes: primary at the bulk-cap negative / SOURCE copper; secondary at R_IS / C_out; quiet grounds join only there | Exactly one join per side | Ground impedance coupling | All | S2 | Graph check: quiet-ground trace segments meet power ground at one pad | PI AN-72 |
| FLY-06 | Primary-secondary separation per section 9; spark gaps and Y-cap per ISO-06/07 | >8 mm (PI device guidance) | Safety, ESD | Offline | S1 | Creepage/clearance checker | PI AN-72, SLUP419 |

### Gaps
- I read no non-PI offline-controller layout guides (for example TI UCC28740 or ST VIPer) in pass 2. PI's guidance is device-specific but widely representative.

---

## 11. Motor drivers and H-bridges

### Takeaway
TI's motor-driver layout guide gives these rules:
- Treat the half-bridge switch node and the supply → HS FET → winding → LS FET → return loop as critical.
- Small ceramic bypass caps (<10 µF) go right at each half-bridge, and bulk electrolytics (>10 µF) at the power entry.
- Gate traces ≥20 mil, routed alongside their return (the switch node for the high side).
- Low-side shunts sit between the LS source and the power-stage star ground, with a tightly coupled differential pair to the current-sense amplifier and ~1 nF caps at the CSA pins. Use net ties to force Kelvin routing.
- VDRAIN sensing is a single Kelvin trace to the HS drain.
- The thermal pad gets continuous pours and direct-connect thermal vias.

Two of its numbers are physically suspect: the via thermal resistance and the "90° bends reflect" claim (see the myth notes below).

### Cited Findings
- **[P] TI SLVA959B "Best Practices for Board Layout of Motor Drivers" (rev. Oct 2021):**
  - **Grounding:** single-point distribution is recommended for power distribution traces, star ground for signal traces. Use partitioning (separate areas, not a physical split). On 2-layer boards, "grid" the ground (connect ground fills and traces at both ends to form a mesh). Use a ground plane on 4-layer or larger 2-layer boards. Keep vias apart so they do not break the plane.
  - **Predriver:** with a predriver, isolate the predriver's high-current ground from the rest of the IC's ground and join them at the star or single point.
  - **2-layer boards:** power-stage FETs, bootstrap circuits and charge pumps are noisy, so keep them away from sensitive signals.
  - **Bulk caps:** place electrolytics (>10 µF) near the power supply module or the board's power entry, with multiple vias per pad and low ESR.
  - **Charge pump / bootstrap caps:** as close to the driver as possible.
  - **Bypass caps:**
    - As close as possible to the power and ground pins, on the same layer as the IC.
    - No via between the bypass cap and the IC pin; route vias into the cap first, then to the IC.
    - Use the most vias and widest traces practical.
    - Closer is better ("less than 0.5 cm, 0.2 in").
    - Length-to-width ratio ≤ 3:1.
  - **Power-stage bypass:** small ceramics (<10 µF) placed as close as possible to the switching-current source (the MOSFETs and motor connection).
  - **CSA decoupling:** with integrated CSAs, add ~1 nF decoupling as close to the sensing pins as possible.
  — [TI SLVA959](https://www.ti.com/lit/pdf/slva959)
- **[P] SLVA959B routing and power stage:**
  - Gate-drive traces wide and short, starting at 20 mil for 1 oz copper.
  - Route the high-side gate trace and the switch-node trace as close together as possible (minimum loop area; dv/dt noise).
  - Use teardrops on thin-to-thick and via-to-pad transitions (mechanical and thermal stress).
  - Route sense signals as parallel pairs around obstacles.
  - Place in-path passives (series resistors, AC-coupling caps) side by side, not staggered.
  - Half-bridge placement can be "stack" or "side-by-side". Minimize the length and maximize the width of the HS-source to LS-drain connection, because switch-node ringing is an LC effect of PCB and FET parasitics.
  - High-current loop = supply+ → HS FET → winding → opposite LS FET → supply−. Use correct widths, minimal distances, and minimal layer jumps, with adequate via count where jumps are unavoidable.
  - VDRAIN (V_DS monitoring for overcurrent protection) is a single Kelvin trace straight to the HS FET drain, with a net tie near the drain to avoid false OCP trips.
  — [TI SLVA959](https://www.ti.com/lit/pdf/slva959)
- **[P] SLVA959B current sensing:**
  - High-side shunt near the star point between the supply and the HS FET sources. For high-side CSAs with external gain resistors, place the first divider resistor nearest the shunt and the rest nearest the device.
  - Low-side shunt between the LS FET source and the power-stage star ground. In 2- or 3-phase sensing, each shunt goes between its LS source and the star ground.
  - Route sense signals as a tightly coupled differential pair from the shunt to the CSA. Place a net tie between the device and the shunt to enforce this during placement.
  - Do not route sense traces parallel to switching signals.
  - Shunt power trade-off example: 20 A through 1 mΩ dissipates 400 mW and gives only a 20 mV signal.
  — [TI SLVA959](https://www.ti.com/lit/pdf/slva959)
- **[P] SLVA959B thermal and vias:**
  - Use continuous top-layer pours from the thermal pad out to the planes. Use 1.5–2 oz copper where possible.
  - Use direct-connect thermal vias, never thermal-relief spokes, and do not cover them with solder mask (voiding).
  - TI recommends 20 mil pad / 8 mil hole thermal vias ("7.874 × 19.874 mil" in its summary).
  - IPC-2152 via current (1 oz, 10 °C rise): 6 mil 0.2 A, 8 mil 0.55 A, 10 mil 0.81 A, 12 mil 0.84 A, 16 mil 1.1 A.
  - For a copper plane used as a trace, put multiple vias where current enters or leaves the component pins. Avoid via clusters that split the plane.
  — [TI SLVA959](https://www.ti.com/lit/pdf/slva959)

### Inferences

| ID | Rule | Numeric guideline | Why | Applies | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|---|
| MOT-01 | Per half-bridge: HF ceramic bypass from HS drain to LS source pads, same layer, no vias between | Cap ≤ ~5 mm (TI: <0.5 cm) from the FET pads; L/W ≤ 3 | Commutation loop inductance causes switch-node overshoot (V_DS stress) | Gate-driver + discrete FETs | S1 | Loop polygon {C_byp, Q_HS.D, Q_LS.S}; via count | SLVA959 |
| MOT-02 | Switch node short and wide between HS source and LS drain | Minimize length/width ratio | Ringing LC | Discrete half-bridges | S2 | Per-phase SW net copper: length / min width | SLVA959 |
| MOT-03 | Gate trace paired with its return (HS: SH node; LS: LS source / PGND) | ≥20 mil @1 oz; short | Gate-loop inductance; dV/dt pickup | Predrivers | S2 | GHx/SHx parallel-run coupling; trace width | SLVA959, EPC (sec. 1) |
| MOT-04 | Shunt between LS source(s) and the star ground; Kelvin pair to the CSA through net ties; ~1 nF at the CSA inputs | Pair tightly coupled; no parallel run with SW or gate nets | mV-level signals near A-level di/dt | Low-side / phase sensing | S1 | Net-tie presence; diff-pair rule; coupling scan | SLVA959 |
| MOT-05 | VDRAIN Kelvin trace directly to the HS drain (net tie) | Single trace | False overcurrent trips from plane IR/L drop | DRV83xx-class | S1 | Net-tie at the drain; trace not shared with the VM pour | SLVA959 |
| MOT-06 | Bulk electrolytic(s) at the power entry with multi-vias; ceramics at the bridge | >10 µF bulk; <10 µF HF | Low-frequency vs high-frequency current supply | All | S2 | Cap classification by value/type; distance to entry vs to bridge | SLVA959 |
| MOT-07 | Driver thermal pad: continuous pour + direct-connect via array; 2 oz if possible | Via array per section 18 | Driver dissipation | Integrated-FET drivers | S2 | Via count in EP; zone connection = solid for thermal vias | SLVA959, SNVA419 |

**Myth / error notes (SLVA959):**
- Its Equation 4 claims 5.73 °C/W for a single 20 mil / 8 mil thermal via. The arithmetic treats the 20 mil pad diameter and the 8 mil hole as radii and the annulus as solid copper. A plated barrel is far more resistive: SNVA419 gives 261 °C/W for a 12 mil via with 0.5 oz plating, and the blog estimates in section 5 are ~150 °C/W. Do not use 5.7 °C/W per via.
- Its Equation 2 prints λ as "25 °C·cm/W", but Equation 3 uses 0.25. The result (71.4 °C/W for a 1 cm² square of 1 oz) matches 0.25.
- Its claim that a 90° bend "acts as an impedance and can cause the current to reflect" is not credible at motor-drive frequencies (see section 3 myth notes). Obtuse corners remain fine for manufacturability.
- Its via-current table (0.84 A at 12 mil) is roughly half the calculator figures quoted in section 2 (about 1.9 A for 0.3 mm). The conservative TI/IPC-2152 table is the safer constraint default.

### Gaps
- I read no stepper- or BLDC-specific layout notes beyond SLVA959, and no data on motor-connector placement and cable shielding.

---

## 12. LED drivers

### Takeaway
LED drivers are switching converters: buck, boost or buck-boost hot-loop rules from section 1 apply. The extra requirements:
- The LED-current sense pair (CSP/CSN) runs in parallel, short and away from the switching node and ground shield, with an RC filter at the IC.
- Do not let switching current flow under the device.
- COMP sits at its pin.
- Large GND copper for the IC and, separately, thermal design for the LEDs (MCPCB is not covered here).

### Cited Findings
- **[P] TI TPS922050/1 datasheet (65 V, 1–2 A buck LED driver), layout guidelines:**
  - A large GND plane for electrical and thermal performance. VIN and GND traces as wide as possible.
  - Thermal vias to other layers.
  - Input caps as close as possible to the VIN and GND pins; VCC cap as close as possible to the VCC pin.
  - SW trace as short as possible (transient spikes, EMI).
  - "Do not allow switching current to flow under the device."
  - CSN and CSP traces in parallel, short, and away from the high-voltage switching trace and the ground shield.
  - Compensation cap as close as possible to COMP.
  - Its design example uses 100 Ω R_FLT at CSN (noise injection, robustness) and an optional 1 nF / 50 V X7R C_FLT across CSP–CSN.
  — [TI TPS922050 datasheet](https://www.ti.com/lit/ds/symlink/tps922050.pdf)
- [S] TPS92201 (synchronous buck LED driver): input/output caps and the inductor as close as possible to the IC. — [TPS92201 datasheet](https://www.mouser.com/datasheet/2/405/1/tps92201-3384073.pdf)

### Inferences

| ID | Rule | Numeric guideline | Why | Applies | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|---|
| LED-01 | Apply the section 1 hot-loop rules by topology (buck LED driver: CIN–IC–diode loop; boost LED driver: SW–D–COUT loop) | As section 1 | Same physics | All switching LED drivers | S1 | As PWR-01/09 | TPS922050 |
| LED-02 | CSP/CSN as a parallel pair from the sense resistor to the IC, filter R/C at the IC pins | Pair; ≤ a few mm of unshielded length near SW (heuristic) | mV sense signals; flicker from coupled edges | High- or low-side LED sense | S1 | Diff-pair rule; coupling scan vs SW net | TPS922050 |
| LED-03 | No switching-current copper under the IC footprint | Keep-out for SW/hot-loop copper under the IC on adjacent layers | Coupling into internal analog | Per datasheet | S2 | Zone/track intersection with IC courtyard on L1/L2 for SW/hot nets | TPS922050 |
| LED-04 | LED strings: copper area and thermal path sized for LED power; keep LEDs (heat) away from the driver's sense and reference parts | Section 18 methods | LED Vf and lifetime are temperature-dependent | Lighting boards | S2 | Thermal estimator | Inference |

### Gaps
- I did not read MCPCB/LED thermal layout guidance or boost/SEPIC LED-driver (high-voltage output) layout notes in pass 2.

---

## 13. Battery chargers and BMS (battery monitors / protectors)

### Takeaway
- **Switching chargers** are buck (or buck-boost) converters with an explicit, *ordered* layout priority in the datasheet. BQ25895: (1) input cap at PMID/GND; (2) inductor at SW with minimal-area copper and "do not use multiple layers in parallel" for SW; (3) output cap near L and IC; (4–5) AGND and PGND joined at one point under the IC; (6) decoupling next to pins; (7) EP soldered with thermal vias; (8) vias sized for current.
- **BMS monitors** need Kelvin sensing at the pack shunt, with the RC filter at the IC (not at the shunt) and the shunt traces routed in parallel. Cell-input RC filters are sized together with balancing. Wide high-current paths. Spark gaps and HV spacing between cell taps and pack terminals.

### Cited Findings
- **[P] TI BQ25895 datasheet §11.1 (SLUSC88C):**
  - Minimize switching-node rise and fall times, and minimize the high-frequency current loop to prevent field radiation and resonance.
  - TI gives a priority list and says "Layout PCB according to this specific order is essential":
    1. Input cap as close as possible to the PMID and GND pins, with the shortest copper or the GND plane.
    2. Inductor input terminal as close as possible to SW. Minimize this copper area but keep it wide enough for the charge current. "Do not use multiple layers in parallel for this connection." Minimize parasitic capacitance to other traces.
    3. Output cap near the inductor and IC, with its ground tied to the IC ground by short copper or the plane.
    4. Route analog ground separately from power ground. Join them using the power pad as the single connection point, or a 0 Ω resistor.
    5. Make that single AGND–PGND tie just beneath the IC. Use a ground copper pour but keep it away from power pins.
    6. Decoupling caps next to the IC pins.
    7. The exposed pad must be soldered, with sufficient thermal vias to the ground plane.
    8. Via size and count sufficient for the current path.
  - Electrical minimums from the same datasheet: PMID needs ≥8.2 µF without OTG, and 40 µF (≤2.4 A) or 60 µF (≤3.1 A) with OTG.
  — [TI BQ25895 datasheet](https://www.ti.com/lit/ds/symlink/bq25895.pdf)
- **[P] TI BQ76952 datasheet §18.1 (battery monitor/protector, 3–16S):**
  - "The quality of the Kelvin connections at the sense resistor is critical." The sense resistor's TC must be ≤50 ppm. Paralleled resistors are OK if Kelvin sensing is preserved. The device is designed to support a 1 mΩ sense resistor.
  - Use 100 Ω from the sense-resistor terminals to SRP/SRN, with 0.1 µF across SRP–SRN (and optional 0.1 µF from each to ground).
  - "All filter components should be placed as close as possible to the device, rather than close to the sense resistor, and the traces from the sense resistor routed in parallel to the filter circuit." A ground plane around the filter network adds noise immunity.
  - REG18 decoupling as close to the pin as possible, with minimal trace inductance, to a ground plane tied to VSS.
  - I2C pins benefit from a Zener + series resistor for ESD.
  - The reference layout is 2-layer, 2.75 × 3.9 in, with cell connections on the left edge and pack connections on the top edge. It uses wide trace areas for high-current paths and PCB spark gaps (E prefix).
  — [TI BQ76952 datasheet](https://www.ti.com/lit/ds/symlink/bq76952.pdf)
- [S] TI E2E on BQ76952 cell inputs: typically 20 Ω series per cell input with a 0.22 µF filter cap (1 µF also acceptable). R can rise to 100 Ω for more filtering at reduced balance current, but no further, or measurement errors appear. — [TI E2E BQ76952 input cell filtering](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/942712/bq76952-input-cell-filtering)
- [S] TI SLUAA81: the minimum input filter resistance for internal balancing is 20 Ω, and the typical internal balance FET R_DS(on) is 25 Ω. Each balancing cell adds current into the top cell input (VC16), causing an IR drop on its resistor. — [TI SLUAA81](https://www.ti.com/lit/pdf/sluaa81)

### Inferences

| ID | Rule | Numeric guideline | Why | Applies | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|---|
| CHG-01 | Follow the charger's ordered priority list exactly (PMID/VBUS input cap → L at SW → COUT → AGND/PGND single tie under the IC → decoupling → EP vias) | As datasheet | Charger = buck converter + sensitive ADC/ILIM/TS sensing | Switching chargers | S1 | Order-of-placement check (tags); PWR-01 loop check on {C_PMID, PMID, PGND} | BQ25895 |
| CHG-02 | SW copper on **one layer only** (no paralleled-layer SW) | — | Parallel layers increase SW area and parasitic C (E-field radiation, capacitive loss) | Chargers; good default for all bucks | S2 | SW-net copper present on >1 layer → flag | BQ25895 |
| BMS-01 | Pack shunt: 4-wire Kelvin; SRP/SRN RC filter at the IC; shunt traces routed as a parallel pair to the filter | 100 Ω + 0.1 µF diff (BQ76952) | Integrating ADC sees µV signals; shunt pad IR | BMS current sense | S1 | Filter parts nearer the IC than the shunt; diff-pair rule | BQ76952 |
| BMS-02 | Cell-tap RC filters placed at the monitor IC; cell traces routed in order (no crossing) from the connector; balance resistors (external balancing) spread for heat and away from the monitor and NTCs | 20–100 Ω / 0.1–1 µF (part-specific) | Measurement accuracy; balancing heat | Cell monitors | S2 | Distance of filter parts to IC pins; thermal spread of balance resistors | BQ76952, E2E, SLUAA81 |
| BMS-03 | High-current path (pack+, pack−, FETs, shunt) as wide pours, kept off the monitor's ground/signal area; the monitor ground ties to the pack-negative side of the shunt as the datasheet specifies | Section 14 sizing | IR drop in shared ground corrupts the cell measurement | Battery packs | S1 | Shared-copper analysis between the high-current path and VSS of the monitor | BQ76952 (wide traces), inference |
| BMS-04 | Spacing between cell taps / pack terminals scales with stack voltage (section 9 tables); PCB spark gaps at pack terminals | e.g., 16S Li-ion ≈ 67 V max → functional spacing (IPC-2221B) | Arcing, transients during cell connection | Multi-cell | S1 | Net voltage classes from the cell index | BQ76952, SLUP419 |

### Gaps
- I read no primary layout guidance for daisy-chained BMS (isoSPI/ADI LTC681x, TI BQ79616): analog.com was blocked and the search budget ran out.
- I did not read linear-charger or power-path (load-sharing) layout guides.

---

## 14. High-current paths and busbars

### Takeaway
Size high-current copper by IPC-2152 (or the conservative IPC-2221). Use thicker copper only where needed: fab minimum track/space grows with copper weight, from 4 mil at 1 oz to 12 mil at 4.5 oz at JLCPCB. Parallel vias at the points where current enters or leaves pads, using conservative per-via ratings (0.5–1 A per 8–16 mil via at 10 °C rise, per TI/IPC-2152). Keep ≤3:1 length/width on decoupling connections. For tens to hundreds of amps, use bolted or press-fit busbars, where the press-fit transition (100–200 µΩ) and the PCB layout around it are the limits.

### Cited Findings
- **[P] JLCPCB minimum track/space by copper weight:** 1 oz 0.10/0.10 mm; 2 oz 0.16 (2L) / 0.15 (ML) mm; 2.5 oz 0.20; 3.5 oz 0.25; 4.5 oz 0.30 mm (2-layer only above 2 oz). Multilayer outer copper is limited to 1–2 oz. — [JLCPCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities)
- **[P] TI SLAA896 (class-D layout), parasitics table** (FR-4, 1 oz, 62 mil board, epoxy-filled vias):
  - Output trace, width (mil) → DC resistance (mΩ/inch) / current (A): 30 → 9.68 / 3.18; 40 → 7.08 / 3.63; 50 → 5.58 / 4.32; 80 → 3.41 / 5.55.
  - Epoxy-filled via, diameter (mil) → R (mΩ) / L (nH) / I (A): 4 → 2.9 / 1.61 / 1.4; 6 → 2.1 / 1.48 / 1.53; 10 → 1.3 / 1.32 / 2.01; 12 → 1.1 / 1.26 / 2.21; 18 → 0.7 / 1.14 / 2.72.
  — [TI SLAA896](https://www.ti.com/lit/pdf/slaa896)
- **[P]** TI SLVA959 via current (IPC-2152, 1 oz, 10 °C): 8 mil 0.55 A, 10 mil 0.81 A, 12 mil 0.84 A, 16 mil 1.1 A. Put multiple vias where current enters or exits pins. "Minimize the number of layer jumps in the high current path." — [TI SLVA959](https://www.ti.com/lit/pdf/slva959)
- Conflict: SLAA896 (2.21 A at 12 mil) and SLVA959 (0.84 A at 12 mil) differ by about 2.6× for nominally similar vias. The likely causes are different temperature-rise assumptions and plating models; neither document states them fully. Use the SLVA959/IPC-2152 figure as a conservative default.
- **[P]** TI SNVA419 copper-weight guidance for DC-DC converters: ≥1 oz for all designs, 2 oz above 3 W, 4 oz above 6 W dissipation. — [TI SNVA419](https://www.ti.com/lit/pdf/snva419)
- **[P] Würth Elektronik ICS PowerBusbar PCB overview:**
  - Copper busbars are pressed together with press-fit Powerelements and the PCB in one operation, with no extra fixing.
  - Assembly order: Powerelement → PCB → busbar.
  - A busbar can replace thick-copper PCBs or copper inlays.
  - Current capacity "must be considered in the context of the overall system". It depends on the PCB layout, the Powerelements, the busbar design and the external supply connection.
  - PCBs must follow IPC-A-600 and the Würth press-fit specification.
  — [Würth PowerBusbar overview](https://www.powerelement.com/media_content/pdf1/product-overview-powerbusbar-pcb-en.pdf)
- [S] Würth PowerBusbar datasheet values: busbar 1.0–1.5 mm thick; PCB up to 2.0 mm FR-4; press-in force 60–350 N per pin, retention 60–80% of press-in force. The limiting factor is usually the PCB layout or the external connection, with press-fit transition resistance 100–200 µΩ. — [Würth PowerBusbar (dwd)](https://www.we-online.com/files/pdf1/dwd---powerbusbar.pdf)
- [S] Laminated (overlapping, opposite-current) DC-link conductors cancel magnetic fields and reduce parasitic inductance (vendor blog). — [AtlasPCB heavy copper](https://www.atlaspcb.com/blog/heavy-copper-pcb-design-power-electronics-bus-bar/)

### Inferences

| ID | Rule | Numeric guideline | Why | Applies | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|---|
| HC-01 | Each high-current net gets I_max; compute min width per layer (IPC-2152/2221) and IR drop; widen or pour | e.g., 1 oz external, 10 °C: ~0.30 mm/A at 1 A (IPC-2221); scale non-linearly | Temperature rise; regulation | Nets > ~1 A | S2 | Narrowest cross-section along every path (graph of tracks/zones) | IPC formula, SLAA896 |
| HC-02 | Layer transitions use ≥ ceil(I / I_via) vias, placed at the pad where the current enters or leaves, not scattered | I_via default 0.8 A (12 mil, 1 oz, 10 °C, TI) | Via ampacity; current crowding | All power transitions | S2 | Count vias within r of each pad on high-current nets | SLVA959 |
| HC-03 | Copper weight is a stackup decision; fine-pitch parts on a heavy-copper layer may violate fab min-space | ≥2 oz → ≥0.15–0.16 mm space at JLCPCB | Etch limits | Heavy copper | S1 | Footprint pad gaps vs fab min-space for the chosen weight | JLCPCB |
| HC-04 | Opposite-current conductors (supply/return) run overlapped on adjacent layers or side by side, never as a wide loop | Minimize enclosed area | Inductance, radiated field | DC links, motor/battery paths | S2 | Loop-area metric for supply+/return pairs | AtlasPCB (low), physics |
| HC-05 | Busbar/press-fit zones: keep-outs per press-fit spec; don't route sensitive nets under busbars; treat transitions as the hot spots | 100–200 µΩ per transition (Würth [S]) | I²R at contacts | >~30–50 A | S2 | Rule areas from busbar footprints | Würth |
| HC-06 | High-current shunts: Kelvin pads; pads not shared with the power path between the sense points | See sections 1, 11, 13 | Pad and solder IR | All shunts | S1 | Sense taps inside pad region | SLVA959, BQ76952 |

### Gaps
- I did not read the IPC-2152 chart data, the Würth press-fit hole specification, or copper-inlay / embedded-coin design rules.

---

## 15. Precision analog and sensor front ends: thermocouple, strain gauge (bridge), photodiode TIA

### Takeaway
Each sensor class has a different dominant error mechanism, and layout rules follow from it:
- **Thermocouple:** unintended thermocouple junctions and gradients. Make connections symmetric and isothermal, with the cold-junction sensor on the isothermal block.
- **Bridge:** lead and trace resistance, and parasitic thermocouples. Use a ratiometric reference, 6-wire Kelvin sense, and short balanced traces.
- **High-speed photodiode TIA:** capacitance at the inverting node. Remove the plane under it and keep the feedback C/R tight.
- **Ultra-low-current TIA / electrometer:** leakage. Use guard rings on both sides and low-leakage parts.

The two TIA regimes give opposite rules on copper near the input, so the system must classify the regime first.

### Cited Findings
- **[P] TI SBAA274 ("A Basic Guide to Thermocouple Measurements"):**
  - "Any connection between two different metals creates a thermocouple junction. Connections from the thermocouple to the ADC should be simple and symmetric to avoid unintentional thermocouple junctions." The resulting errors matter when there is a temperature gradient across the board or device.
  - Both thermocouple return leads must be at the same known temperature, using a cold-junction (isothermal) block, often a connector with large metal mass. "In some applications, it may be sufficient to maximize the copper fill around the junctions of the PCB, layering the connection between metal fill between top and bottom layers." An enclosure may be needed against air currents.
  - The CJ reference is measured with a diode, thermistor or RTD. Any error in the CJ measurement goes directly into the result.
  - Seebeck coefficients (µV/°C at 0 °C): J 50.37, K 39.48, T 38.74, E 58.70.
  — [TI SBAA274](https://www.ti.com/lit/pdf/sbaa274)
- **[P] TI SBAA532A ("A Basic Guide to Bridge Measurements"):**
  - A six-wire bridge uses the V_SENSE± leads as a Kelvin (force-sense) connection, which removes lead-resistance error and makes the ADC V_REF equal to the voltage actually driving the bridge (ratiometric).
  - Parasitic thermocouples outside the sensor create temperature-varying offset, and ADC bias current through lead and filter resistances adds offset.
  - AC excitation, which swaps the excitation polarity and subtracts the two phases, cancels offsets such as parasitic thermocouples.
  — [TI SBAA532A](https://www.ti.com/lit/an/sbaa532a/sbaa532a.pdf)
- **[P]** TI TIDUB00 (single-supply strain-gauge bridge reference design), PCB layout: bridge and common-mode resistor traces "as short and balanced as possible to minimize ... a differential voltage in the signal chain due to trace impedance mismatch". The terminal block is placed (bottom side) to allow close connection of the input resistors. The gain-set resistor R_G goes as close to the amplifier pins as possible (stray capacitance, trace impedance). Solid ground plane, decoupling close. — [TI TIDUB00](https://www.ti.com/lit/pdf/tidub00)
- **[P]** TI TIDU535 (1 MHz single-supply photodiode amplifier): parasitic capacitance at the inverting input can make the circuit unstable. "For this reason, the ground pour of the PCB is removed in the areas around the inverting input of the op amp on both layers." A feedback capacitor C_F is necessary for stability in most photodiode amplifiers. A 49.9 Ω output resistor isolates cable and connector capacitance and matches 50 Ω coax, with a 50 Ω microstrip to the output connector. — [TI TIDU535](https://www.ti.com/lit/pdf/tidu535)
- **[P]** TI SBOA034 (low-input-current FET op amps / switched integrator): guarded input, and the "circuit must be well shielded". Resistors typically have ~0.5 pF of stray capacitance, which matters in the feedback network. Low-leakage, low-dielectric-absorption capacitor types: NPO/C0G ceramic, polycarbonate, polystyrene, silver mica. — [TI SBOA034](https://www.ti.com/lit/an/sboa034/sboa034.pdf)
- [S] For a femtoampere TIA, guard the through-hole cathode pin on the bottom side of the board too. The thread cites Paul Grohe's low-leakage articles. — [TI E2E LMP7721 TIA layout](https://e2e.ti.com/support/amplifiers-group/amplifiers/f/amplifiers-forum/1271048/lmp7721-transimpedance-amplifier---question-about-layout-guard-and-copper-pours)
- **[P]** Ott's ADC LSB table (section 4) sets the analog ground-noise budget: for example 12-bit / 1 V → 240 µV, 16-bit → 15 µV. — [Ott tech tip](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html)
- **[P] Jim Williams AN47 (1991):** 1 pF of parasitic capacitance across a 1 kΩ feedback resistor caused severe peaking. "Minimize trace area and stray capacitance at critical nodes. Consider layout as an integral part of the circuit." — [LT AN47 (MIT mirror)](https://www.mit.edu/~6.331/an47fa.pdf)

### Inferences

| ID | Rule | Numeric guideline | Why | Applies | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|---|
| SEN-01 | Thermocouple input: the connector forms an isothermal block (copper pours on both layers, stitched); the CJ sensor (thermistor/RTD/IC) sits on that block; both TC traces route symmetrically, same layer, same vias | CJ sensor within the connector's copper island; matched trace geometry | Seebeck error ~40 µV/°C (K) per degree of gradient between junctions | TC inputs | S1 | CJ-sensor distance to TC connector; symmetry of the TC± routes (length, via count, layer) | SBAA274 |
| SEN-02 | Keep heat sources away from the TC connector/CJ block and the input path; isotherm symmetry | Distance from >0.5 W parts (heuristic ≥15–20 mm) | Gradient → error | TC, bridge, precision DC | S2 | Thermal-distance check | SBAA274 |
| SEN-03 | Bridge: ratiometric reference (excitation also drives V_REF), 6-wire Kelvin sense to the connector, bridge-completion and input resistors with short, balanced traces; R_G at the INA pins | Equal length/geometry for ± paths | Lead/trace R mismatch, gain error | Load cells, strain | S1 | Pairwise length/geometry matching; R_G pin distance | SBAA532A, TIDUB00 |
| SEN-04 | Classify TIA regime: **high-speed** (BW ≳ 100 kHz, R_F ≲ 1 MΩ) → remove GND pour under and around the IN− node on all layers; **ultra-low-current** (fA–pA, R_F ≳ 100 MΩ) → driven guard ring at IN+ potential, both sides incl. TH pins, mask-free guard, low-leakage parts | Regime thresholds are heuristic | Capacitance-limited vs leakage-limited | Photodiode, electrometer | S1 | Copper-area check under the IN− net on all layers, or guard-net presence | TIDU535, SBOA034, ADI (sec. 4) |
| SEN-05 | R_F ∥ C_F placed directly across the op-amp IN− and OUT pins; the IN− node has the shortest copper; the photodiode next to IN− | Summing-node copper minimal | 0.5–1 pF strays rival C_F | TIAs | S1 | IN− net total copper length/area | SBOA034, AN47 |
| SEN-06 | Ground-noise budget = LSB / k: select single-plane partitioning (≤12 bit) vs isolated analog regions tied under each ADC (≥14 bit) | Ott LSB table | Ground noise must stay < LSB | ADC systems | S2 | Rule chooses the partition strategy from ADC resolution in the BOM | Ott |

### Gaps
- I did not obtain primary RTD-specific layout notes (3- and 4-wire excitation routing) or ADI AN-43 (Williams, bridge circuits); analog.com was blocked, and the search budget ended before a mirror was found.
- No numeric thresholds for the TIA regime split were found; they are mine.

---

## 16. Audio (class-D power stages, low-frequency grounding)

### Takeaway
Class-D amplifiers are switching power stages with quantified loop-inductance budgets. TI TAS2xxx targets a total supply-to-ground decoupling loop inductance (pin-to-pin plus capacitor ESL) of 750–1150 pH, with the smallest cap within 1 mm of the pin. Other rules:
- Switching outputs never run next to other signals on adjacent layers without a ground layer between.
- Vsense lines are differential pairs tapped at the speaker terminals.
- EMC filter and snubber parts sit near the IC, with output terminals connected to the filter-cap pads.
- Inputs go on the quiet side, shielded by ground floods.

Below roughly 100 kHz, return currents no longer hug the signal trace, which is why star grounding and careful return-path engineering still apply to analog audio and precision low-frequency systems.

### Cited Findings
- **[P] TI SLAA896 ("PCB Layout Guidelines for TAS2xxx Series Class-D Boosted Audio Amplifier"):**
  - Four to six layers with epoxy-filled vias is ideal.
  - Short all ground pins together at the device balls on the top layer, stitched to a solid L2 ground under the device with multiple vias on or next to the balls, so there are no multiple ground loops. A dedicated ground layer is strongly recommended.
  - "The smallest decoupling cap is placed less than 1 mm of distance from the device pin and any further caps are placed next to it." Use multiple vias at the cap pads.
  - Table 2, optimum loop parasitics, pin-to-pin + cap ESL = total (pH): DREG-GND 650 + 500 = 1150; GREG-PVDD 300 + 500 = 800; VBAT-GND 650 + 500 = 1150; VBST-BGND 250 + 500 = 750; VDD-GND 350 + 500 = 850.
  - Class-D output, SW node and Vsense must not run in an adjacent layer next to any other signal without ground shielding between the layers.
  - The boost SW trace must carry 5 A (device-dependent).
  - Vsense taps as close to the speaker terminals as possible, 6 mil wide, routed differentially.
  - Connect VBST to PVDD strongly right under the device on the top layer (avoids IR droop and via inductance).
  - AVDD/VDD/IOVDD run as star-connected 20–30 mil traces from the PMIC.
  - Charge-pump cap star-connected at the PVDD pin, not on the PVDD plane.
  — [TI SLAA896](https://www.ti.com/lit/pdf/slaa896)
- **[P] TI TPA3110D2 class-D layout/EMC slides:**
  - Place the IC at the centre of the ground plane, with the PowerPAD on thermal vias of 0.33 mm diameter on 1.0 mm centres.
  - High-frequency decoupling caps within 1 mm of the IC, bulk caps as close as possible to them, grounded through multiple vias.
  - EMC snubbers and filters very near the IC. Filter caps as close to the IC as possible, grounded through the plane.
  - Connect the output terminals to the filter-cap pads, directly or through broad copper, which minimizes unfiltered loops.
  - Put inputs on the "quiet" side, shielded with top and bottom ground floods.
  - Ground analog control caps (GVDD, PLIMIT, AVCC) through the plane with multiple vias, and the AGND pin to the PowerPAD (the centre of the ground system).
  — [TI TPA3110D2 PCB layout/EMC slides](https://e2e.ti.com/cfs-file/__key/telligent-evolution-components-attachments/00-06-00-00-00-05-21-80/PCBlyt_2D00_home_2D00_ent_2D00_audio_2B00_EMC_2B00_T_2D00_100818.pdf)
- **[P] Altium, "PCB Ground Plane Best Practices" (Z. Peterson):**
  - Default to a uniform ground plane. Do not split ground into multiple pour regions unless galvanic isolation or a safety or standards reason requires it.
  - Corner case: audio and precision analog below ~100 kHz, where "return currents ... do not follow closely to the trace". There, carefully engineered return paths or isolation, and star grounding of power entry against ground loops, may be preferred.
  — [Altium ground plane best practices](https://resources.altium.com/p/pcb-ground-plane-best-practices-your-multilayer-stackup)
- [S] TI's 2000 class-D layout article (TPA005D1x/TPA032D0x) recommends a continuous ground plane and terminating power-section decoupling caps near their ground pins. — [TI SLYT182](https://www.ti.com/lit/an/slyt182/slyt182.pdf)
- [S] Keep the class-D output filter loop small, put the speaker connector close to the filter, and stitch filter grounds to the plane. — [EE Times class-D layout](https://www.eetimes.com/circuit-board-layout-guidelines-for-class-d-amplifiers/)

### Inferences

| ID | Rule | Numeric guideline | Why | Applies | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|---|
| AUD-01 | Decoupling loop-inductance budget per supply pin (estimate from geometry): pin-to-pin ≤ 250–650 pH plus cap ESL | Smallest cap ≤1 mm from the pin | Boost and class-D current edges | Class-D, boosted amps; reusable for any IC whose datasheet gives an L budget | S2 | Loop-inductance estimator (pad gap, via count/length, plane depth) vs budget | SLAA896 |
| AUD-02 | Switching outputs (OUT±, SW, BST) never adjacent-layer to other signals without an intervening GND layer | — | Broadside coupling | Class-D | S2 | Layer-overlap scan: SW-class tracks vs other nets on L±1 | SLAA896 |
| AUD-03 | Output EMC filter (L/ferrite + C) at the IC; the speaker connector connects at the filter-cap pads; snubbers at the IC | Unfiltered copper minimal | Radiated EMI from the unfiltered loop | Filtered class-D | S2 | Distance IC → filter caps; connector → cap pads | TPA3110 slides, EE Times |
| AUD-04 | Inputs on the quiet side away from outputs, with ground floods top and bottom; AGND to the EP centre | — | Input pickup of output switching | Amplifiers | S2 | Region partition: input nets vs output nets distance | TPA3110 slides |
| AUD-05 | Low-frequency analog audio (<~100 kHz): plan return paths explicitly; star the power entry and avoid ground loops through connectors/chassis; do not rely on "return under trace" | — | At low frequency, return current spreads by resistance rather than inductance | Line-level audio, precision DC | S2 | Flag shared ground copper between high-current returns (amp output, LED, motor) and audio input references | Altium (Peterson) |

### Gaps
- I could not research "pin 1 problem" / cable-shield-to-chassis practice (Muncy, Rane notes) or analog audio grounding from primary sources before the search budget ran out.

---

## 17. PDN design methodology in depth: target impedance and its limits, flat impedance, tools, plane resonance

### Takeaway
Target impedance (Z_t = ΔV_allowed / I_transient) is necessary but not sufficient:
1. Allocate only the dynamic-transient part of the noise budget to Z_t; VRM ripple, IR drop and crosstalk use the rest.
2. Design for a **flat** impedance profile below Z_t.
3. Where peaks remain, keep each parallel-resonance peak ≤ 1.57 × Z_t for a fully robust PDN (many shipped products tolerate ~3 ×). Watch for "rogue waves" when several high-Q peaks exist.

Damping (ESR-controlled caps, or few distinct values with controlled ESR) matters as much as capacitance. Plane-pair cavities resonate at f₁₀ ≈ c / (2·a·√εr), roughly 720 MHz for a 100 mm FR-4 plane. Capacitor-vendor tools (Murata SimSurfing, KEMET K-SIM) give the bias- and frequency-dependent models needed to compute the profile.

### Cited Findings
- **[P] Smith, Sandler & Bogatin, "Target Impedance Is Not Enough" (Signal Integrity Journal, 2019):**
  - Target impedance only manages voltage excursions from dynamic current transients. The total regulation budget also includes VRM ripple, DC regulation, IR drop and crosstalk, so use only the allocated fraction in Z_t.
  - A flat impedance profile below Z_t is "the basic criterion for a 'robust' PDN".
  - Each impedance peak is a parallel RLC, characterized by its resonant frequency, peak impedance, characteristic impedance Z₀ and Q.
  - Step response: if the rise time is <3.5 ns (bandwidth >100 MHz) and the resonance is below 100 MHz, the response is a damped sine. The peak is governed by Z₀, so Z₀ ≤ Z_t is the next criterion.
  - A square wave of current at the resonant frequency drives excursions of 0.64 × Q × the step-response noise, reached after about Q cycles. Hence the robust limit is peak impedance ≤ 1/0.64 = 1.57 × Z_t.
  - "Many successfully deployed products have a peak height as large as 3× the target impedance."
  - Several high-Q peaks excited in sequence can build a "rogue wave" that exceeds the limit even if each peak meets it.
  — [SIJ "Target Impedance Is Not Enough"](https://www.signalintegrityjournal.com/articles/1083-target-impedance-is-not-enough)
- **[P]** Archambeault conclusions (see section 2): maximize capacitance within each package size; spread caps; alternate pin orientation; deep plane pairs mean higher inductance; avoid long thin power structures. — [Archambeault slides](https://ewh.ieee.org/r3/enc/emcs/archive/2012-10-10b_DecouplingMyths.pdf)
- [S] Keysight's application note argues that flat impedance across the required band is the best way to avoid rogue voltage waves, and covers choosing capacitor values to avoid resonant peaks. — [Keysight "Optimize PDNs for Flat Impedance"](https://www.keysight.com/us/en/assets/3119-1097/application-notes/5992-4272.pdf)
- [S] Witcher & Sandler (DesignCon 2023) propose supplementing target impedance with flatness metrics: Q, group delay, and NISM (non-invasive stability measurement). — [DesignCon 2023 paper](https://www.picotest.com/wp-content/uploads/2024/09/DesignCon2023_New_Power_Integrity_Requirement_to_Supplement_Target_Impedance_Witcher_Sandler-2.pdf)
- [S] Sandler: bulk capacitance follows from plane (or interconnect) inductance and target impedance as C = L / R². — [Sierra Circuits interview with Sandler](https://www.protoexpress.com/blog/steve-sandlers-insights-on-power-integrity-pdn-design-and-high-speed-simulations/)
- [S] Novak and colleagues compared PDN synthesis methods (multi-pole, capacitors-by-the-decade) in time and frequency domains. Related patents choose capacitor banks per frequency band with series resistance ≤ Z_t (ESR-controlled), and capacitor count N = ESR / Z_t(f). — [Novak et al., DesignCon 2006](http://electrical-integrity.com/Paper_download_files/DC06_TF-MP3_SUN.pdf); [USPTO 6571184](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/6571184)
- [S] Plane-pair cavity modes: f_mn = (c₀ / 2√εr)·√((m/a)² + (n/b)²). The first mode for a 100 mm FR-4 board (εr ≈ 4.3) is ~723 MHz. At resonance, plane impedance spikes, and vias passing through hot spots couple noise into signals. Distributed stitching vias and decoupling lower Q. — [rftools PDN cavity resonance](https://rftools.io/blog/pdn-impedance-analyzer); [PCD&F: PDN behaviour is a geometry problem](https://www.pcdandf.com/pcdesign/index.php/current-issue/297-tips-tricks/19402-pcb-power-integrity-analysis-why-pdn-behavior-is-a-geometry-problem)
- [S] Murata SimSurfing (free, online) provides capacitance vs DC bias and temperature, impedance and ESR vs frequency, and S-parameter / SPICE model export for Murata MLCCs. KEMET K-SIM simulates capacitors over frequency, temperature, ripple and voltage, can combine parallel parts, and exports CSV/SPICE/S2P. Both are vendor-locked, and no open-source PDN calculator was found. — [Murata SimSurfing MLCC](https://ds.murata.com/simsurfing/mlcc.html?lcid=en-us); [KEMET K-SIM](https://eu.mouser.com/en/new/kemet-electronics/kemet-ksim-simulation-tool/)

### Inferences
Suggested automated PDN workflow (each step is code, not LLM judgement):
1. From the BOM and datasheets, list rails: V, ΔV budget, I_transient (or I_max × activity factor), and the frequency band (VRM bandwidth up to the IC's package or die resonance). Z_t = (fraction × ΔV) / I_transient.
2. Build an impedance model:
   - VRM as R + L above its bandwidth.
   - Each MLCC with DC-bias-derated C (SimSurfing/K-SIM data or a derating table), ESR and ESL.
   - Mounting inductance from geometry (pad-to-via distance, via length to the plane pair; section 2 numbers).
   - Plane-pair C = ε·A/d and spreading inductance.
3. Check: |Z(f)| ≤ Z_t across the band. Each anti-resonance peak ≤ 1.57 × Z_t (hard for "robust"; soft ≤ 3 × Z_t). Report Q per peak. Warn when ≥2 peaks have Q > ~2 (rogue-wave risk).
4. Fix by adding same-value caps (lower ESL), choosing values whose ESR sets damping near Z_t, or adding a controlled-ESR bulk cap (C ≈ L/R² per Sandler) rather than piling up many decade values.
5. Compute f₁₀/f₀₁ for each plane pair from the board outline. Flag when clock harmonics or switching-edge content fall within ±10% of a cavity mode. Then add stitching vias and decoupling at mode maxima (board edges and corners for the lowest modes).

| ID | Rule | Numeric guideline | Why | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|
| PDN-09 | Peak impedance ≤ 1.57 × Z_t (robust) or ≤ 3 × Z_t (accepted risk) | — | Resonant square-wave excitation | S2 | RLC network sweep | SIJ 2019 |
| PDN-10 | Prefer flat profile / controlled-ESR damping over many decade values | Q ≲ 1–2 per peak | Rogue waves, anti-resonances | S3 | Q extraction per peak | SIJ 2019, Keysight [S], Novak [S] |
| PDN-11 | Plane-pair cavity-mode check vs clock/edge spectrum | f₁₀ ≈ 150 / (a[mm]·√εr) GHz ≈ 720 MHz at a = 100 mm, εr 4.3 | Plane impedance spikes at modes | S3 | Formula on outline; harmonics list from netlist clocks | rftools [S], physics |
| PDN-12 | Plane pairs high in the stackup (near the IC side); thin dielectric; no long thin power necks | — | Effective inductance rises with depth and narrowness | S3 | Stackup position; neck width/length analysis of power zones | Archambeault [P] |

### Gaps
- I did not read the Keysight app note or the Novak DesignCon paper in full (Keysight served an HTML asset page, and the search budget ended).
- No open-source PDN impedance tool was identified, so the workflow above implies building one (simple lumped RLC is adequate for board-level screening).

---

## 18. Thermal design methodology: thermal-resistance networks, copper area vs temperature rise, metrics

### Takeaway
- Do not compute T_J from datasheet R_θJA except as a comparison. R_θJA is a property of the JEDEC test board, and 70–95% of the heat leaves through the board. PCB design is its strongest influence (TI ranks it 100%).
- Build a resistive network instead: junction → (R_θJC or Ψ_JB) → copper → planes (lateral R = L / (λ·W·t)) → vias → board surface → air (h ≈ 10 W/m²K). Superpose multiple sources.
- TI's rules of thumb:
  - ≥15.3 cm² (2.37 in²) of two-sided solid copper per watt for a 40 °C rise in still air (airflow up to halves it).
  - Board area ≈ 500 °C·cm²/W / (θ_JA,required − θ_JC).
  - Thermal vias ~261 °C/W each (12 mil, 0.5 oz), in an array at 1 mm pitch.
  - ≥1 oz copper; 2 oz above 3 W; 4 oz above 6 W.
  - Avoid copper breaks perpendicular to heat flow.
  - A heatsink works better on the board bottom under the exposed pad than on a plastic package top (θ_JT 50–200 °C/W).

### Cited Findings
- **[P] TI SPRA953D ("Semiconductor and IC Package Thermal Metrics", rev. 2024):**
  - R_θJA is the most commonly reported and most often misused metric. It measures a package mounted on a specific JEDEC test coupon (EIA/JESD51), and in still-air measurements "almost 70%–95% of the power generated by the chip is dissipated from the test board".
  - Factors affecting R_θJA, as rules of thumb: PCB design strong (100%); chip/pad size strong (50%); internal package geometry strong (35%); altitude strong (18%); ambient temperature weak (7%); power dissipation weak (3%).
  - 1s vs 2s2p test boards can shift R_θJA by up to 50%.
  - Use R_θJA(effective) measured or modelled in the actual system.
  - Ψ_JT (JESD51-2) is typically 0.5–2 °C/W for plastic packages vs R_θJC of 4–15 °C/W. T_J = T_top + Ψ_JT × P.
  - Ψ_JB lets you back-calculate T_J from a board thermocouple. Do not use Ψ_JT when a heatsink is attached.
  — [TI SPRA953](https://www.ti.com/lit/pdf/spra953)
- **[P] TI SNVA419C (AN-2020 "Thermal Design By Insight, Not Hindsight"):**
  - **Rule 1 (board size):** natural convection, no heatsink, a two-sided PCB with solid copper fills needs ≥15.29 cm² (≈2.37 in²) per watt for a 40 °C rise. Airflow can reduce this "by up to half". Alternatively, Board Area (cm²) ≥ 500 °C·cm²/W ÷ (θ_JA − θ_JC). This assumes the enclosure does not block convection and the EP connects to planes that reach the board edge. Internal ground planes on a 4-layer board improve even a good 2-layer design by up to 30%.
  - **Rule 2 (thermal vias):** a typical 12 mil through via with 0.5 oz sidewalls is 261 °C/W. "Place as many thermal vias as will fit underneath the exposed pad to form an array, with 1mm spacing", connected to as many copper layers as possible, with as solid a bottom ground as possible.
  - **Rule 3 (copper thickness):** ≥1 oz for all DC-DC designs, 2 oz above 3 W, 4 oz above 6 W. Example: a 3 × 3 in 2-layer board went from θ_JA 28.3 °C/W at 1 oz to 21.2 °C/W at 2 oz, a 25% improvement.
  - **Rule 4 (breaks):** a cut perpendicular to heat flow caused a 5.5 °C rise, against 1.5 °C for a cut parallel to it. Run traces through heat spreaders radially from the source.
  - **Rule 5 (heatsink placement):** θ_JT of plastic package tops is 50–200 °C/W, so a bottom-side heatsink through EP and vias beats a top-mounted one.
  - **Rule 6:** superposition "almost works" because the network is slightly non-linear.
  - Model constants: λ_Cu ≈ 4 W/cm·K; FR-4 λ ≈ 0.0023 W/cm·K; h ≈ 10 W/m²K board-to-air. A 1 cm² square of 1 oz copper laterally is ~71 °C/W, and the FR-4 vertical resistance for a 1 cm² area is ~13.9 °C/W.
  — [TI SNVA419](https://www.ti.com/lit/pdf/snva419)
- **[P] TI SLMA002H (PowerPAD thermally enhanced package):**
  - The thermal land goes directly under the package. For TQFP, the maximum copper land size is the package body size minus 2.0 mm, with a solder-mask-defined pad.
  - Thermal-via benefit shows diminishing returns. For a small die, 5–9 vias should be adequate. The example patterns use 0.33 mm (13 mil) vias plated with 1 oz copper, a barrel copper cross-section of ≈1% of the land area.
  - TI does not recommend leaving a PowerPAD unsoldered.
  — [TI SLMA002](https://www.ti.com/lit/pdf/slma002)
- **[P] TI SLVA959B (thermal):**
  - Use continuous pours from the thermal pad, and direct-connect (not thermal-relief) thermal vias, not covered by mask.
  - Thermal relief joints "reduce the flow of heat".
  - Doubling copper thickness halves the plane's lateral thermal resistance.
  — [TI SLVA959](https://www.ti.com/lit/pdf/slva959)

### Inferences
A screening thermal estimator the placer can run on every candidate placement:
1. **Power per part:** LDO (VIN−VOUT)·I; switcher losses ≈ P_out·(1/η − 1), split IC/inductor/diode by datasheet or heuristic; resistors I²R; LEDs (1 − efficiency)·P.
2. **Spreading area per part:** the connected copper on each layer reachable through the EP/pad and vias (flood-fill on the zone graph), clipped to a radius where lateral R exceeds a cutoff.
3. **Network:** R_J→pad (θ_JC or Ψ_JB) + R_via-array (261 °C/W ÷ N for 12 mil/0.5 oz; scale for drill and plating) + lateral copper R = L/(λ·W·t) + R_surface→air = 1/(h·A_effective, both sides).
4. **Superpose** sources by influence coefficients (SNVA419 Rule 6).
5. **Check:** T_J < T_J,max − margin. Sensitive parts (Al-electrolytics, crystals, references, CJ sensors) stay within their allowed temperature, and their ΔT relative to neighbours stays small (section 5 TH-06).

| ID | Rule | Numeric guideline | Why | Sev | Auto-check | Basis |
|---|---|---|---|---|---|---|
| TH-09 | Never size copper from R_θJA alone; use a network or Ψ-based estimate | — | R_θJA is board-defined | S2 | Estimator above | SPRA953 |
| TH-10 | Minimum copper area per watt | ≥15.3 cm²/W two-sided solid, still air, 40 °C rise | Convection limit | S2 | Connected copper area vs P | SNVA419 |
| TH-11 | EP via array at 1 mm pitch, as many as fit, connected to every plane layer, direct-connect (no spokes), not mask-covered (or plugged per assembly) | 0.30–0.33 mm drill | 261 °C/W per via; parallel | S2 | Via pitch/count; zone connection style = solid | SNVA419, SLMA002, SLVA959 |
| TH-12 | Copper weight by dissipation | 1 oz base; 2 oz >3 W; 4 oz >6 W | Lateral spreading | S3 | Stackup vs total P | SNVA419 |
| TH-13 | No copper breaks perpendicular to heat flow near hot parts; route through spreaders radially | — | 5.5 °C vs 1.5 °C example | S3 | Detect slots/tracks cutting the pour within r of hot parts, measure angle to radial | SNVA419 |
| TH-14 | Heatsink on the board bottom under the EP rather than on a plastic top | θ_JT 50–200 °C/W | Series resistance | S3 | Heatsink footprint side vs EP | SNVA419 |

### Gaps
- I did not obtain JEDEC JESD51-7 board definitions or copper-area vs θ_JA curves for specific packages (TI SLVA462-type data).
- No CFD or FEA validation is in scope. The estimator is first-order, and SNVA419 itself says it does not replace FEA.

---

## 19. Practitioner material: Robert Feranec (FEDEVEL), Phil's Lab, Bob Pease, Jim Williams

### Takeaway
The practitioners agree with the app notes but add workflow and judgement points that matter for automation:
- **Feranec:** big parts and connectors first; leave room between the processor and memory; push high-current parts away from sensitive areas; decoupling under BGAs; termination resistors at the driver, EMI/ESD parts at the connector; one via per BGA power pad; fan out DDR first and shortest, inner pads first.
- **Phil's Lab:** rough placement first, then section-by-section refinement, with decoupling and crystal placement as their own steps; solid reference planes; no splits under traces.
- **Pease:** "the art of knowing which circuits are critical isn't always written down ... wrapped up in the heads of experts"; thermals, crosstalk and grounds are what CAD automation tends to ignore; hard mixed-signal isolation may need separate boards or shields.
- **Williams:** a ground plane exists to minimize inductance; 1 pF can wreck a fast loop; bypass combinations can ring; treat layout as part of the circuit.

### Cited Findings
- **[P] Bob Pease, "What's All This Layout Stuff, Anyhow?"** (Electronic Design, 17 Jan 2008, reprinted in the TI "Bob Pease Lab Notes" compilation):
  - CAD advocates "did not want to talk about thermals. Or crosstalk. Or good grounds, even."
  - Layouts done "as quickly as possible" led to "hot transistors with varying quantities of dissipation, adjacent to critical transistors. Noisy busses laid out alongside (or on top of!) critical analog circuits."
  - "The art of knowing which circuits are critical isn't always written down, codified, or quantified. Some of those things are just wrapped up in the heads of experts."
  - On matching: there are "more than 50 rules for making transistors and resistors that match", and common-centroid layout "is usually very easy, using the rules of symmetry".
  — [Bob Pease Lab Notes Part 7 (TI E2E PDF)](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/1023/Bob-Pease-Lab-Notes-Part-7.pdf)
- **[P] Pease, mailbag (same compilation), on putting analog and digital that need high isolation on one board:**
  - Build the circuits separately, possibly with the analog section in a shielded box, and merge them only if lucky. Be prepared to mount copper fences, walls and screens between the sections.
  - He suggests 35 dB of rejection is feasible, while 50 dB "will probably take all those extreme efforts".
  - For the bench, use a grounded copper-clad sheet as a ground plane.
  — [Bob Pease Lab Notes Part 7](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/1023/Bob-Pease-Lab-Notes-Part-7.pdf)
- **[P] Jim Williams, LT AN47 "High Speed Amplifier Techniques" (1991):**
  - "Ground planes are primarily useful for minimizing circuit inductance". The return current flows directly under the signal conductor, and "10nH at 100MHz has an impedance of 6Ω".
  - Practical hints:
    1. Ground-plane as much area as possible, especially under high-frequency traces.
    2. Mount components carrying fast currents (terminations, ICs, transistors, decoupling caps) as close to the board as possible.
    3. Where common ground potential matters (comparator inputs), single-point the critical components into the plane, trading lower inductance against single-pointing.
    4. Keep traces short.
  - Bypassing is "by far the most common error" in high-speed amplifier work. No supply or regulator has zero output impedance at 100 MHz.
  - Electrolytic + ceramic combinations help, but "the right (wrong) combination of supply line parasitics and paralleled dissimilar capacitors can produce a resonant, ringing response".
  - "Minimize trace area and stray capacitance at critical nodes. Consider layout as an integral part of the circuit". 1 pF across a 1 kΩ feedback resistor caused severe peaking.
  - Probe ground leads should not exceed 1 in for fast work, and ideally coaxial board-mounted probe points should be used.
  — [LT AN47 (MIT mirror)](https://www.mit.edu/~6.331/an47fa.pdf); [ADI canonical URL](https://www.analog.com/media/en/technical-documentation/application-notes/an47fa.pdf)
- **[P-sec] Feranec's Advanced PCB Layout course, as described by a student review:**
  - Lesson 1: "put big components first, leave some room between MPU and DDRs, put the high current components as far as" possible.
  - Then decoupling caps underneath BGA chips (iterative, with fanout tips).
  - Termination resistors "as close as possible to the main component", while EMI filters and ESD protection go close to the connectors.
  - Use 3D models during placement.
  - Fanout: power pins first, with 0.3 mm through vias to the bottom-side decoupling caps. "One and only one via per each power pad. Don't share a power via among the tracks of the same net!"
  - Then data signals with microvias. DDR is the most critical and is fanned out first and shortest, inner pads first. On the DDR chip, data fans out outward and address inward. Use the same topology within a group. Fan out all BGA pads.
  - Rules quoted: 20H for power planes, via aspect ratio ≤10.
  - Routing: read the vendor layout guide first (for example NXP DDR3 order: address, differential pairs, control, data). Route groups "piece by piece" and from both ends.
  — [Helentronica review of FEDEVEL Advanced PCB Layout](https://helentronica.com/2017/05/03/advanced-pcb-layout-course-by-fedevel-academy/)
- [S] A FEDEVEL tip: add extra silkscreen information on connectors and slots to prevent placement problems (too close, wrong rotation). — [FEDEVEL Tip #041](https://fedevel.com/blog/tip-041-add-more-information-on-silkscreen-of-some-components-connectors-slots)
- **[P] Phil's Lab course outlines:**
  - The KiCad hardware course goes from system design to a 4-layer KiCad 6 board.
  - The advanced course covers grounding, sectioning and crosstalk; build-up, stack-up and controlled impedance; PDN choice and capacitor placement for QFP/QFN/BGA; DDR3 (fly-by, byte-lane swapping, delay matching); Gigabit Ethernet (RJ45 and PHY placement, QFN fan-out, chassis connection); USB HS / eMMC; manufacturing outputs.
  — [Phil's Lab courses](https://www.phils-lab.net/courses)
- [S] Phil's Lab's 2-layer tips: keep all components on one layer with a solid ground fill on the other, and minimize vias that cut the reference plane. Altium material by the same author: no splits in the reference plane under traces, and decoupling caps close to pins with short, wide traces and clustered power vias. — [Phil's Lab #137 summary](https://daily.dev/posts/sponsored-2-layer-pcb-design-tips---phil-s-lab-137-ecpsukgvc); [Altium high-speed PCB design tips](https://resources.altium.com/p/high-speed-pcb-design-tips)
- [S] A community tips list credited to Feranec's videos repeats "smaller cap closer to IC", 10 µF + 100 nF pairs, and "connectors on one edge". It is third-party and should not be treated as Feranec's exact words; compare with the myth notes in section 2. — [hemalchevli/Tips-and-tricks](https://github.com/hemalchevli/Tips-and-tricks)

### Inferences
- Pease's point that criticality is tacit, not codified, is the strongest argument for the LLM's role in this system: classifying which nets and parts are critical (thermal neighbours, noisy buses, matched pairs, summing nodes) from schematic semantics and datasheets, and passing that to deterministic geometry checks. A "criticality map" should be an explicit, reviewable artefact.
- Feranec's "one via per BGA power pad, never shared" and "fan out every pad" convert directly into fanout-generator constraints. "DDR first, inner pads first" becomes a fanout ordering heuristic.
- The 20H rule (Feranec course) is contested in the EMC literature. I could not fetch a primary rebuttal before the search budget ended, so encode it as optional/soft, not as a default constraint.
- Williams's ringing bypass combinations and Archambeault/Bogatin's value-mixing findings (sections 2 and 17) agree. The system should damp (ESR) rather than add decade values.

### Gaps
- I read no Phil's Lab video transcripts. YouTube transcripts were not fetched, and his written content is mostly course outlines. Feranec's placement method is known only from a student review and FEDEVEL blog snippets.
- Pease's "Common Centroid Stuff" column (ED Online 6121) and other Pease grounding columns were not retrieved.

---

## 20. Implications for an LLM-driven KiCad placer/router

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

**G. Extensions from pass 2 (sections 9–19):**
- **More role detectors to add** (netlist pattern → roles → loops/constraints):
  - **Offline flyback:**
    - Pattern: transformer with a primary winding to the HV bulk-cap net, plus an IC or FET drain on the other primary end. Classify the windings: primary / secondary / bias.
    - Roles: clamp (diode + RC or TVS across the primary); Y-cap (cap whose pins are on primary and secondary ground or rail classes); spark-gap footprints; post-filter L (series L after C_OUT before the connector).
    - Constraints: FLY-01…06, ISO-01…07.
  - **H-bridge / 3-phase:**
    - Pattern: pairs of N-FETs sharing an SH node that goes to a connector; gate-driver pins GHx/SHx/GLx/SLx/SPx/SNx/VDRAIN/VCP.
    - Roles: per-phase bypass cap, shunt, CSA filter caps, bulk cap.
    - Constraints: MOT-01…07.
  - **Charger:** pins PMID/VBUS/SW/BAT/REGN/BTST/ILIM/TS. Emit the datasheet's *ordered* priority list as `placement_priority` (BQ25895), plus the CHG-02 SW single-layer rule.
  - **BMS:**
    - Pattern: pins VC0…VCn, SRP/SRN, BAT, PACK, CHG/DSG gate drivers.
    - Roles: cell-filter RCs (at the IC), pack shunt (Kelvin pair; filter at the IC), protection FETs (high-current pour).
    - Spacing classes from cell index × cell voltage.
  - **LED driver:** CSP/CSN pins → sense pair + R_FLT/C_FLT at the IC; SW keep-out under the IC.
  - **Sensor front-ends:**
    - Thermocouple: TC connector footprint, or nets named TC±, plus an NTC/RTD/temperature-sensor IC → CJ-block co-location and symmetric routing.
    - Bridge: excitation/sense/signal nets of a 4/6-wire connector → ratiometric REF and matched routing.
    - TIA: op-amp with R_F ≥ ~100 kΩ and a photodiode on IN− → regime classification (SEN-04) and IN− copper rules.
  - **Class-D:** OUT±/SW/BST/PVDD/VBST/Vsense pins → loop-inductance budgets (AUD-01), no adjacent-layer coupling (AUD-02), filter at the IC (AUD-03).
- **A loop-inductance estimator as a first-class metric.** SLAA896 gives explicit pH budgets (750–1150 pH total, 250–650 pH pin-to-pin), and section 2 gives measured mounting inductances (≈0.44–0.63 nH for an 0402 on top). A geometric estimator lets the placer score "as close as possible" numerically instead of with arbitrary mm thresholds. The inputs are the pad-to-pin gap, trace W/L, via count and length to the reference plane, and plane depth (Archambeault: deeper means higher L).
- **Safety-spacing engine.** Implement section 9 as a deterministic lookup: (V_RMS, V_impulse from OVC, PD, MG/CTI, altitude, grade) → (creepage, clearance). Then add a surface-path creepage checker (2-D geodesic on the board surface, respecting slots ≥ PD minimum width) and a 3-D clearance checker. The LLM's job is only to classify nets and insulation grades from the schematic and product context, and those classifications must be confirmed by a human because they are safety-critical.
- **Thermal screening per placement** (section 18 estimator) and **PDN screening per rail** (section 17 workflow) are cheap enough to run in the placement loop. Both need part power and rail data that the LLM extracts from datasheets and the schematic.
- **Criticality map (Pease).** Before placement, the LLM emits a reviewable list of the critical items:
  - hot loops;
  - high-Z / summing nodes;
  - matched pairs (symmetry constraints);
  - thermal aggressors and victims;
  - noisy buses and their sensitive neighbours;
  - isolation barriers.
  Each item carries severity and provenance. Deterministic checks consume this map, and a human can correct it before any geometry is generated.
- **Tag provenance on generated constraints.** Each constraint should carry its source URL and an authority level ([P] datasheet/app note > [P-sec] > [S] > heuristic), so that conflicts are resolved by authority. Examples: via-current tables differing 2.6× (SLVA959 vs SLAA896); spark gap 5.4 vs 6.4 mm inside AN-72; SLVA959's erroneous via thermal resistance.

### Gaps
- No published system or paper was found in this session that auto-extracts hot loops from netlists. The algorithm above is a proposal and needs validation on real designs (e.g., a corpus of open-source KiCad boards with known regulators).
- I could not consult KiCad's custom-rules documentation here (the network was blocked). The rule syntax mentioned must be checked against the installed KiCad version.
- The default numeric thresholds (pad gaps, loop-area caps, keep-out distances) are uncalibrated heuristics. They should be tuned against reference layouts from TI, ADI and Espressif evaluation boards.
