# High-Speed Digital, Signal Integrity, Differential Pairs and EMI/EMC: A Machine-Actionable Catalog of PCB Placement and Routing Rules

> **Method note for the report writer.** WebFetch (and direct curl) to ti.com, docs.kicad.org, learnemc.com and resources.altium.com was blocked by the session's egress policy (DNS `ENOTFOUND` / proxy `connect_rejected`). Every citation below therefore comes from WebSearch result content: snippets and quoted passages from the cited URLs, not full-document reads. Numbers were kept only when the search result quoted them from the named source. Where a number came only from a secondary or vendor blog, it is labelled as such. Unit conversions (mil to mm, ps to mm) are arithmetic, using 1 mil = 0.0254 mm and roughly 150 µm/ps in FR-4 (that figure is from [Toradex](https://docs.toradex.com/102492-layout-design-guide.pdf) and [AtlasPCB](https://www.atlaspcb.com/blog/differential-pair-routing-tight-vs-loose-coupling/)).
>
> **Rule-table schema used throughout:** `ID | Rule | Numeric guideline | Why (physics) | Applies when | Sev | Auto-check | Source`. Severity: **P0** = functional failure or spec violation likely; **P1** = margin, EMC or compliance risk; **P2** = good practice. Auto-check: **K** = encodable as native KiCad DRC or a net-class constraint; **G** = needs a custom geometric or physics checker outside KiCad DRC; **S** = needs simulation (field solver or channel simulation).

---

## 1. Return-path fundamentals (current under the signal, plane continuity, split crossing, reference changes, loop area)

### Takeaway
At high frequency, return current flows in the reference plane directly under (adjacent to) the signal trace, because the fields are concentrated in the dielectric between the trace and its nearest plane. Any interruption of that plane, whether a split, a void, an unbridged reference change or a far-away plane, forces the return current to detour. The detour enlarges loop inductance and area, which raises crosstalk, impedance discontinuity, common-mode current and radiation. The single most important high-speed rule is therefore "every fast signal has a continuous, adjacent reference plane, and every layer change has a nearby return-path bridge."

### Cited Findings
- Bogatin lists "a continuous return path adjacent to every signal path" as a best design practice to follow as a habit (item in his "20 Rules for Engineers"). — [Bogatin, Signal Integrity Journal](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers)
- Bogatin, on split ground planes: "a wide, continuous ground plane adjacent to a signal trace will be the lowest cross talk configuration. Anything other than a wide plane means more cross talk between signal paths sharing this return conductor." (Cited via a search summary of his SIJ article; the specific URL was not returned. The general return-path tutorial is [Teledyne LeCroy / Bogatin](https://www.teledynelecroy.com/oscilloscope/blog/signal-return-paths-signal-and-power-integrity-tutorial/).) — [Bogatin SIJ rules page](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers)
- Rick Hartley: "The energy in an electrical circuit is not in the current or voltage; it is in the electric and magnetic fields. And those fields don't exist in the traces or in the planes – they exist in the spaces between them." He treats a signal plus its return as a waveguide. Return current follows the field, not the geometric shortest path (his metal-table demonstration shows the return does not take the hypotenuse). — [EEJournal "Matters of Integrity"](https://www.eejournal.com/article/matters-of-integrity/); [Proto Express: Hartley tips](https://www.protoexpress.com/blog/7-pcb-design-tips-by-rick-hartley/)
- Hartley: a ground plane placed "two or three dielectrics away" from the signal layer causes signal degradation. Several signal layers all referencing one plane produce "all fields intermingling in the dielectric space, all coupling energy into one another", which he links to EMI. Problems are tied to rise time, not clock frequency. — [Altium: Stack-up best practices with Rick Hartley](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley); [Proto Express: Hartley on EMI](https://www.protoexpress.com/blog/rick-hartley-pcb-design-recommendations-to-minimize-emi/)
- TI SPRAAR7: route high-speed signals over a solid GND reference plane, "not across a plane split or a void in the reference plane unless absolutely necessary." Keep high-speed differential signals at least **1.5 W** (1.5 × trace width) away from voids in the reference plane. TI advises against referencing power planes. — [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7); [SPRAAR7F mirror](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/qoriq-grl/9543/1/High_speed_interfaces_layout_spraar7f.pdf)
- TI SPRAAR7: if the GND reference changes across a layer transition, "via-stitch both GND planes together"; place stitching vias "symmetrically within **200 mils** (center-to-center, closer is better) of the signal transition vias." — [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7)
- GND-to-GND transitions: place the ground stitching via close to the signal via ("within a few hundred micrometers" in one source, "ideally within 40 mils" in another; both secondary). GND-to-PWR transitions cannot use a via because the planes are DC-isolated, so use a stitching capacitor of about **1–10 nF** within about **50 mil** of the signal via (secondary). The capacitor works only below its self-resonant frequency, because its series inductance limits it. If both layers reference the same plane, no bridge is needed. — [AtlasPCB via transitions](https://www.atlaspcb.com/blog/pcb-via-transition-return-current-path-signal-integrity/); [UGPCB return vias](https://www.ugpcb.com/news/pcb-tech/electronic-design/high-speed-signal-layer-transitions-the-science-of-return-vias-in-pcb-design/); [JLCPCB return path](https://jlcpcb.com/blog/return-path-pcb-precision-fabrication)
- Ott (mixed-signal): if a plane must be split, connect the halves at one location (a bridge) and route **all** crossing traces over the bridge, so each has a return path directly underneath and a small loop. Opto-isolators or transformers are the other acceptable ways to cross a split. — [Ott, EE Times "Partitioning and Layout of a Mixed-Signal PCB"](https://www.eetimes.com/partitioning-and-layout-of-a-mixed-signal-pcb-3/); [Ott tech tip](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html)
- Measured: in a gapped-ground-plane study (Clemson/UMR), increasing gap length produced significant increases in common-mode current. A trace crossing a gap raises the partial inductance of the return path. — [Effects of Gapped Groundplanes and Guard Traces on Radiated EMI (EMCS97-159)](https://cecas.clemson.edu/cvel/pdf/EMCS97-159.pdf)
- "Common-mode currents cannot flow on a PCB with an infinite ground-return plane." Ground-plane voltage drop from net inductance drives common-mode emissions. — [NTIA ground-plane inductance report](https://its.ntia.gov/publications/download/98-344.pdf)

#### Rule table
| ID | Rule | Numeric | Why | Applies when | Sev | Check | Source |
|---|---|---|---|---|---|---|---|
| RP-1 | Every high-speed or controlled-impedance trace has an adjacent, continuous reference plane (prefer GND) along its full length | none | Fields and return current live in the dielectric under the trace; a break forces a detour, so L and loop area rise | Edge rate fast relative to trace length (see §5), all diff pairs, clocks | P0 | G: project each segment onto the adjacent-layer copper polygons, flag any segment over no copper | [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7); [Bogatin](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers) |
| RP-2 | Do not route over plane splits or voids; keep clear of void edges | ≥1.5 W from void edge (TI) | Fringing fields reach the void edge, so impedance and return path are disturbed | Diff pairs, high-speed SE | P0 | G: buffer the trace by 1.5 W, intersect with void polygons on the reference layer | [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7) |
| RP-3 | On a reference change GND→GND, place a GND stitching via next to each signal via, symmetric for pairs | ≤200 mil (5.08 mm) c-c per TI; closer is better (≈40 mil, ≈1 mm, secondary) | Return current must jump planes; a distant via enlarges the loop | Any layer change where the reference plane changes | P0/P1 | G: for each signal via, find the nearest GND via connecting both reference layers; check distance | [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7); [AtlasPCB](https://www.atlaspcb.com/blog/pcb-via-transition-return-current-path-signal-integrity/) |
| RP-4 | On a reference change GND↔PWR (or PWR↔PWR), place a stitching capacitor near the via, or avoid the change entirely | 1–10 nF within ≈50 mil (secondary) | DC-isolated planes need an AC bridge; capacitor ESL and SRF limit effectiveness | Layer change where reference plane nets differ | P1 | G: identify reference nets above and below; search for a capacitor between those nets within radius R | [UGPCB](https://www.ugpcb.com/news/pcb-tech/electronic-design/high-speed-signal-layer-transitions-the-science-of-return-vias-in-pcb-design/); [JLCPCB](https://jlcpcb.com/blog/return-path-pcb-precision-fabrication) |
| RP-5 | If a split is unavoidable, provide a bridge and route every crossing trace over it | none | Keeps the return directly under the signal | Mixed-signal or isolated domains | P0 | G: every trace crossing the split boundary must lie within the bridge polygon | [Ott EE Times](https://www.eetimes.com/partitioning-and-layout-of-a-mixed-signal-pcb-3/) |
| RP-6 | Prefer GND over PWR as the reference for high-speed nets | none | A power-plane reference's return must pass through decoupling caps | High-speed interfaces | P1 | G: reference-plane net lookup per trace segment | [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7) |
| RP-7 | Keep the reference plane on the immediately adjacent layer, not 2–3 dielectrics away | Adjacent layer | Field containment; lower loop inductance | Stackup design | P1 | K/G: stackup audit (signal layer to nearest plane distance) | [Altium/Hartley](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley) |

### Inferences
- Return-path continuity is the rule with the largest consequence and the least native support in KiCad DRC. It should be the first custom geometric checker built (see §11–12). The check needs per-segment knowledge of the adjacent reference layer, taken from the stackup, and of the copper (zone fill) on that layer. Zone fills must be computed first.
- "Loop area" for a trace over a solid plane is roughly trace length × dielectric height. A practical automated proxy is therefore (a) the length of trace not over a plane, (b) the distance from the signal via to the return via at transitions, and (c) the height to the reference. This follows from Hartley's field model and Ott's bridge reasoning above.

### Gaps
- Fetching Rick Hartley's and Lee Ritchey's primary material (talk slides, *Right the First Time*) was blocked. Only secondary summaries were available. No Ritchey-specific numeric claims could be verified.
- No primary source was found for an exact maximum signal-via to return-via distance beyond TI's 200 mil. The 40 mil and 50 mil figures are from vendor or secondary blogs.

---

## 2. Stackup: 2/4/6/8-layer assignments, adjacent reference planes, impedance control (50 Ω SE, 85/90/100 Ω diff)

### Takeaway
Ott's five stackup objectives are the standard framework: (1) every signal layer adjacent to a plane, (2) signals close to their plane, (3) power and ground tightly coupled, (4) high-speed signals buried between planes, (5) multiple ground planes. No single stackup satisfies all five below 8 layers, so the choice is a trade-off. Hubing warns that no single "recipe" fits more than a subset of boards. Impedance targets are interface-driven (50 Ω SE; 85, 90 or 100 Ω differential) and must be produced by a field solver using the fabricator's dielectric data.

### Cited Findings
- Ott's five objectives: each signal layer next to a plane; signals close to reference planes; power and ground tightly paired; high-speed traces on buried layers between planes; multiple ground planes lower reference impedance and common-mode radiation. — [Ott, PCB Stack-Up Part 1](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-1.html)
- 4-layer (Ott): "space the signal layers as close to the planes as possible (**<0.010"**), and use a large core (**>0.040"**) between the power and ground planes." There is an inherent trade-off between close signal/plane coupling (objective 2) and close power/ground coupling (objective 3). Normal 4-layer construction gives insufficient inter-plane capacitance for decoupling. — [Ott, PCB Stack-Up Part 2](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-2.html); [Ott Stack-up PDF](https://frontdoor.biz/HowToPCB/HowToPCB-extra/PCBStackups(Ott).pdf)
- 6-layer (Ott): a 4-layer board with two signal layers added between the planes "improves the EMI dramatically," giving two buried layers for high-speed signals and two surface layers for low-speed signals. — [Ott Stack-up PDF](https://frontdoor.biz/HowToPCB/HowToPCB-extra/PCBStackups(Ott).pdf)
- 8-layer (Ott): the preferred option has every signal layer adjacent to a plane, multiple ground planes and all layers closely coupled. An alternative with planes in the center gives a tight power/ground pair but cannot shield the outer traces (it meets objectives 1, 2, 3 and 5 but not 4). — [Ott, PCB Stack-Up Part 4](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-4.html)
- Hubing ("Not-So-Good EMC Design Guidelines"): no single layer-stack recipe fits more than a small subset of boards, so layer assignment depends on the design. — [LearnEMC Not-So-Good Guidelines](https://learnemc.com/not-so-good-emc-design-guidelines)
- Hartley: improper stackup, with the plane far from the signal layer, degrades signals and fails to contain fields, causing EMI and SI problems. Copper roughness increases loss. — [Altium/Hartley stack-up](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley); [EEJournal](https://www.eejournal.com/article/matters-of-integrity/)
- Impedance targets seen in vendor guides: USB 2.0 **90 Ω ±15%** differential and 45 Ω ±15% SE (TI SLLA414). Microchip USB hub: **90 Ω (+5/−10 Ω)**, SE 40–55 Ω. HDMI and CSI-2 D-PHY **100 Ω** (ADI GMSL2 guide). Renesas CSI/DSI 100 Ω ±20%. Toradex display interfaces 90 Ω ±15%. PCIe **85 Ω ±15%** for add-in cards (secondary) versus 85–115 Ω (Diodes). Qualcomm relaxes the legacy 100 Ω/50 Ω targets on ultrathin boards. — [TI SLLA414](https://www.ti.com/lit/pdf/slla414); [Microchip AN26.2 DS00001876](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf); [ADI GMSL2 UG-2212](https://www.analog.com/media/en/technical-documentation/user-guides/public-gmsl2-hardware-design-and-validation-guide.pdf); [Renesas MIPI/USB/PCIe guide](https://www.renesas.com/en/document/apn/pcb-design-guidelines-mipi-csi-mipi-dsi-usb20-and-pci-express-gen2); [Toradex Layout Guide](https://docs.toradex.com/102492-layout-design-guide.pdf); [PCBSync PCIe](https://pcbsync.com/pcie-pcb-layout/); [Diodes PI2EQX862](https://www.diodes.com/assets/Part-Support-Files/PI2EQX862/PI2EQX862XUAE_App_Combo-ReDriver-APPLICATION-INFORMATION_RevB.pdf); [Qualcomm QRB5165 CSI](https://docs.qualcomm.com/bundle/publicresource/topics/80-PV086-5P/mipi-csi-d-phy-routing-constraints-up-to-2dot5-Gbps.html)
- Bogatin: higher-impedance lines (above 50 Ω) at the same spacing produce more crosstalk, because they are farther from the plane relative to trace width. — [EDN Rule of Thumb #20](https://www.edn.com/how-far-is-far-enough-signal-line-spacing-for-acceptable-near-end-crosstalk-rule-of-thumb-20/)

#### Typical stackups (from Ott's objectives; labels: S = signal, G = ground, P = power)
| Layers | Common assignment | Objectives met / trade-off | Source |
|---|---|---|---|
| 2 | S+pour / G-dominant bottom (route almost everything on top over unbroken bottom GND) | Only a crude reference is possible; Hartley stresses every trace still needs a return path | [Starting Electronics (Hartley grounding)](https://startingelectronics.org/articles/proper-grounding/) |
| 4 | S1 / G / P / S2, with thin prepreg (<0.010") S-to-plane and thick core (>0.040") | Good signal-plane coupling; weak P-G capacitance. Many designers use S/G/G/S or G-S-S-G variants (see Gaps) | [Ott Part 2](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-2.html) |
| 6 | S1 / G / S2 / S3 / P / S4 style: two buried high-speed layers plus two surface low-speed layers | Big EMI improvement; buried signals shielded | [Ott PDF](https://frontdoor.biz/HowToPCB/HowToPCB-extra/PCBStackups(Ott).pdf) |
| 8 | Every S adjacent to a plane, multiple G planes, all closely coupled (Ott's preferred). Alternative: P/G pair in the center | Preferred option meets all five objectives | [Ott Part 4](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-4.html) |

### Inferences
- For the constraint generator: impedance is a stackup property, not a net property. The pipeline should (1) choose or ingest a stackup, (2) compute width and gap per (layer, target Z) with a field solver or KiCad's calculator, and (3) emit per-layer net-class or custom-rule widths. A layer-conditional `track_width` / `diff_pair_gap` rule per impedance class is the natural KiCad encoding.
- Assign high-speed nets preferentially to stripline layers (buried between planes) on 6+ layer boards, following Ott's objective 4. On 4-layer boards they will be microstrip, which has nonzero far-end crosstalk (see §6).

### Gaps
- The exact Ott 6-layer layer ordering could not be confirmed from the snippet. The S/G/S/S/P/S style above is inferred from "two signal layers added between the planes."
- No primary-sourced width/spacing-versus-dielectric formula (for example IPC-2141) was retrieved. Use a field solver.
- No primary source for the popular 4-layer "S/G/G/S" or "G/S/S/G" alternatives was retrieved in this session.

---

## 3. Differential pairs: coupling, intra-pair skew, inter-pair spacing, symmetry, via pairing, ground vias, serpentine placement

### Takeaway
Keep the pair symmetric and its spacing consistent along the whole route, over a solid plane. Match P/N length tightly (commonly ≤5 mil, 0.127 mm, for multi-Gbps SerDes). Fix mismatch with small serpentines close to where the mismatch originates, not at the end of the route. Separate pairs by ≥5 W (TI). Tight versus loose coupling matters less than consistency and an unbroken plane: plane discontinuities still convert differential signals to common mode.

### Cited Findings
- TI SPRAAR7: "the spacing between the signal pairs must be a minimum of **5 times the width** of the trace (5W rule)"; "Route all high-speed differential pairs together symmetrically and parallel to each other." — [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7)
- TI SPRAAR7: skew within any USB3/SATA/PCIe differential pair **≤5 mils**. Skew within a USB 2.0 pair ≤50 mils (DRA7xx/AM57xx table). — [SPRAAR7F mirror](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/qoriq-grl/9543/1/High_speed_interfaces_layout_spraar7f.pdf); [hackaday mirror of SPRAAR7E](https://cdn.hackaday.io/files/11178478239552/spraar7e_USB.pdf)
- TI SPRAAR7: avoid SMDs on high-speed traces. Where required (for example USB SuperSpeed TX AC caps), maximum package 0603, 0402 or smaller strongly recommended, "placed symmetrically." — [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7)
- NXP AN10798 (DisplayPort): limit P/N length difference to **5 mils max**. Added length ("serpentine") belongs at the mismatch point. — [NXP AN10798](https://www.nxp.com/docs/en/application-note/AN10798.pdf)
- NXP AN10373 (PCIe PHY): each jog length at least **15 mils** (3 × the 5 mil trace width). — [NXP AN10373](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/powerquicc/2284/2/philips_PCIe_pcb_routing_guide.pdf)
- Apply length correction as close as possible to the mismatch point (for example near a via or component). The inner trace of a bend is shorter, so compensate at each bend rather than accumulating at the end. Serpentine amplitude should be ≥2 × trace width to avoid self-coupling (vendor). — [Proto Express routing practices](https://www.protoexpress.com/blog/best-high-speed-pcb-routing-practices/); [AtlasPCB impedance and diff pairs](https://www.atlaspcb.com/blog/pcb-impedance-matching-differential-pairs/)
- Rough intra-pair skew targets: <5 ps (≈0.75 mm in FR-4) for 10 Gbps NRZ; <1–2 ps (≈0.15–0.3 mm) for 56 Gbps PAM4 (vendor FAQ). Different via pad locations for P and N are a skew source. — [AtlasPCB tight vs loose](https://www.atlaspcb.com/blog/differential-pair-routing-tight-vs-loose-coupling/)
- Coupling: a secondhand summary of Bogatin says intra-pair coupling matters less than assumed, because most return current still flows in the nearby plane, and constant spacing plus a solid plane matter more than the tightest gap. A ScienceDirect overview argues that tight coupling moves return current onto the partner trace, which reduces sensitivity to plane noise. All sources agree that plane gaps cause differential-to-common-mode conversion. — [Instrumentation Blog diff pair rules](https://www.instrumentationblog.in/differential-pair-routing-pcb/); [ScienceDirect topic](https://www.sciencedirect.com/topics/computer-science/differential-pair); [Bogatin SIJ: does coupling matter for loss](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/482-does-coupling-matter-in-characterizing-the-loss-of-a-differential-pair)
- Bends: older TI USB guidance (SPRAAR7A) says to use two 45° turns or an arc instead of a single 90° turn "to reduce reflections." (Context: see §9 on the 90° myth.) — [hackaday mirror of SPRAAR7E](https://cdn.hackaday.io/files/11178478239552/spraar7e_USB.pdf)
- Via count: TI allows max **2 vias** per USB3 differential trace and up to **4 vias** per USB 2.0 trace (device table). — [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7); [SPRAAR7F](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/qoriq-grl/9543/1/High_speed_interfaces_layout_spraar7f.pdf)
- Ground and stitching vias at diff-pair layer transitions: symmetric, within 200 mil of the signal vias (TI). Distribute stitching vias evenly along both sides of transmission lines for isolation (vendor). — [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7); [AtlasPCB stitching vias](https://www.atlaspcb.com/blog/pcb-ground-plane-stitching-via/)

#### Rule table
| ID | Rule | Numeric | Why | Applies when | Sev | Check | Source |
|---|---|---|---|---|---|---|---|
| DP-1 | Route the pair at the target Zdiff with constant width and gap | Interface-specific (85/90/100 Ω) | Impedance continuity; avoids mode conversion | All diff pairs | P0 | K: net class diff width/gap; custom `diff_pair_gap` | [TI SLLA414](https://www.ti.com/lit/pdf/slla414) |
| DP-2 | Intra-pair skew (P vs N length) | ≤5 mil (USB3/PCIe/SATA/DP); ≤50 mil USB2 (TI); ps targets per data rate | Skew converts differential to common mode, increasing EMI and eye closure | All pairs | P0 | K: `skew` with `within_diff_pairs` | [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7); [NXP AN10798](https://www.nxp.com/docs/en/application-note/AN10798.pdf) |
| DP-3 | Put tuning serpentines near the source of mismatch (bend, via, pad) | Jog ≥3 W / ≥15 mil (NXP PCIe); amplitude ≥2 W (vendor) | Keeps P and N phase-aligned along the route, so less common-mode conversion | Pairs needing tuning | P1 | G: locate the tuning pattern; compute distance to the mismatch feature | [NXP AN10373](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/powerquicc/2284/2/philips_PCIe_pcb_routing_guide.pdf); [Proto Express](https://www.protoexpress.com/blog/best-high-speed-pcb-routing-practices/) |
| DP-4 | Inter-pair spacing | ≥5 W (TI) | Crosstalk between lanes | Multi-lane SerDes | P1 | K: clearance rule between different diff-pair nets of the same class | [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7) |
| DP-5 | Symmetric breakout and symmetric component placement (AC caps, ESD, CMC) | Same package, mirrored | Asymmetry produces skew and mode conversion | Pairs with in-line parts | P1 | G: pad-centroid symmetry about the pair centreline | [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7) |
| DP-6 | Limit vias per trace; via both legs together | USB3 ≤2, USB2 ≤4 (TI) | Each via is a discontinuity and a stub | SerDes | P1 | K: `via_count` max per net | [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7) |
| DP-7 | Limit uncoupled length (fan-out, around obstacles) | Example 3.0 mm in a KiCad forum rule; interface-specific | Uncoupled sections change Zdiff and add common mode | All pairs | P1 | K: `diff_pair_uncoupled (max …)` | [KiCad forum diff_pair constraints](https://forum.kicad.info/t/how-do-the-diff-pair-constraints-work/69785); [KiCad 8 docs](https://docs.kicad.org/8.0/en/pcbnew/pcbnew.html) |
| DP-8 | Keep the pair ≥1.5 W from reference-plane voids; never cross splits | 1.5 W | Mode conversion and return detour | All pairs | P0 | G | [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7) |

### Inferences
- Encoding "serpentine near mismatch" requires knowing where the mismatch arises. Bends accumulate a running skew, and vias with offset pads add skew. A router should therefore track running P−N delay along the path and insert compensation once the running skew exceeds a threshold, rather than only checking total skew. This follows from the AtlasPCB and Proto Express guidance above.
- The ps-based targets (≈150 µm/ps in FR-4) let the generator derive mm tolerances from the interface's unit interval when no vendor number exists.

### Gaps
- No primary source quantified the required distance or count of GND return vias for a differential via pair (beyond TI's 200 mil stitching rule). One search explicitly found nothing on this.
- No primary-sourced numeric definition of "tight" versus "loose" coupling (for example gap ≤ W versus ≥2 W) was retrieved.

---

## 4. Interface-specific rules (USB 2.0/3.x, PCIe, Ethernet, HDMI, MIPI, DDR3/4/LPDDR4, SPI/QSPI, clocks and crystals, SerDes AC caps)

### Takeaway
Interface rules are mostly about impedance class, intra-pair and inter-pair skew, via count, and placement order of in-line parts (AC caps, ESD, CMC, magnetics). The authoritative number is always the device vendor's layout guide for the specific PHY or controller, because limits differ substantially between vendors (especially for DDR). The table below is a starting default set with sources; the generator should let a vendor-guide override replace any value.

### Cited Findings

#### USB 2.0 (HS 480 Mb/s)
- 90 Ω ±15% differential, 45 Ω ±15% SE (TI SLLA414). Microchip: 90 Ω +5/−10 Ω, SE 40–55 Ω, P/N mismatch ≤**50 mil**. TI DRA7/AM57 table: USB2 pair skew ≤50 mil, 81–99 Ω, ≤4 vias. Microchip AN13.10 requires a continuous ground plane under DP/DM. — [TI SLLA414](https://www.ti.com/lit/pdf/slla414); [Microchip AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf); [SPRAAR7F](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/qoriq-grl/9543/1/High_speed_interfaces_layout_spraar7f.pdf); [Microchip AN13.10](https://ww1.microchip.com/downloads/en/Appnotes/AN13.10-Application-Note-DS00002972A.pdf)
- More conservative or looser blog figures exist: match within 2 mil and keep total length under 4 in (embedded-design blog); mismatch within 0.6 in (Altium, 2-layer USB). — [Embedded Hardware Design](https://embeddedhardwaredesign.com/usb2-0-pcb-layout-guidelines/); [Altium USB on 2-layer](https://resources.altium.com/p/routing-requirements-usb-20-2-layer-pcb)

#### USB 3.x / PCIe / SATA (multi-Gb/s SerDes)
- Intra-pair skew ≤**5 mil** (TI; also Diodes and JLCPCB). USB3 ≤2 vias per trace. Via stubs <15 mil, otherwise backdrill. — [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7); [Diodes](https://www.diodes.com/assets/Part-Support-Files/PI2EQX862/PI2EQX862XUAE_App_Combo-ReDriver-APPLICATION-INFORMATION_RevB.pdf); [JLCPCB USB3](https://jlcpcb.com/blog/usb3-differential-signaling-design-guide)
- USB SuperSpeed TX AC coupling caps: 0402 preferred (0603 max), symmetric. TI says keep AC caps, common-mode filter and ESD "as short and close to the connector as possible." JLCPCB places SSTX caps close to the USB connector. — [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7); [JLCPCB USB3](https://jlcpcb.com/blog/usb3-differential-signaling-design-guide)
- PCIe: 85 Ω ±15% (add-in card, secondary). AC caps near the TX end, 0402 (0603 acceptable). Cap value 176–265 nF in current spec, 100 nF acceptable for Gen3 (secondary; verify against PCI-SIG). — [PCBSync PCIe](https://pcbsync.com/pcie-pcb-layout/)
- AC cap pad discontinuity: cut out the reference plane under the AC-cap pads to reduce the capacitive dip (EDN example: mismatch reduced from ~12 Ω to ~2 Ω). ADI EV kits use cutouts of **1.35× pad size**, stackup-dependent. Microchip recommends an anti-pad on the ground layer beneath DC-blocking cap pads. Intel found that a 15 mil reference strip in the void helps for 0201. Benefit is link-dependent, so verify by TDR or channel simulation (SI-LIST). — [EDN improved SMT pad](https://www.edn.com/improved-smt-pad-design-for-high-frequency-signal-transmission/); [ADI GMSL2 UG-2212](https://www.analog.com/media/en/technical-documentation/user-guides/public-gmsl2-hardware-design-and-validation-guide.pdf); [Microchip SerDes guidelines](https://support.microchip.com/s/article/Serdes-PCB-Layout-Guidelines); [Intel 0201 AC cap](https://www.intel.com/content/www/us/en/docs/programmable/683132/current/adding-a-trace-reference-to-the-0201.html); [SI-LIST thread](https://www.freelists.org/post/si-list/Cutout-and-Power-reference-for-AC-coupling-Capacitor,14)

#### Ethernet (10/100/1000BASE-T MDI, magnetics)
- Bob Smith termination: 75 Ω resistors on cable-side center taps to a high-voltage capacitor (1000 pF commonly cited) to chassis ground, "for best EMI performance." A separate chassis-ground region is required (Microchip), to isolate the board from ESD and prevent a common-mode noise path. — [Pulse layout considerations](https://www.mouser.com/pdfDocs/pulse_layout_considerations_final.pdf); [Microchip AN DS00002054A](https://ww1.microchip.com/downloads/en/Appnotes/00002054A.pdf); [Microchip ENT-AN0098 Magnetics](https://ww1.microchip.com/downloads/en/Appnotes/VPPD-01740.pdf)
- Pulse: separate the PHY from the magnetics by ≥**25 mm (~1 in)**; keep the magnetics close (~25 mm) to the RJ45. — [Pulse](https://www.mouser.com/pdfDocs/pulse_layout_considerations_final.pdf)
- Ground under magnetics and RJ45: guidance conflicts. Options seen are a moat between system and chassis ground bridged only by capacitors and high-value resistors, no plane under the connector and magnetics, or a continuous plane (secondary summary). — [PCBSync Ethernet](https://pcbsync.com/ethernet-pcb-layout/); [SIJ: Ethernet connectors over ground planes](https://www.signalintegrityjournal.com/articles/1808-ethernet-connectors-and-routing-above-ground-planes)
- Würth reference design RD016 exists for an Ethernet front end with EMC components (not read in detail). — [Würth RD016](https://www.we-online.com/components/media/o721295v410%20RD016%20EN-GB-Ethernet%20Front%20End.pdf)

#### HDMI / MIPI CSI-2, DSI (D-PHY)
- HDMI 100 Ω differential. CSI-2 D-PHY 100 Ω, avoid 90° corners. Length differences ±5 mil for both intra-pair and inter-pair (ADI GMSL2). Cadence: ≤5 mil within pair. Renesas: 100 Ω ±20%. Toradex: 90 Ω ±15%, intra-pair <1 ps (~150 µm), clock-to-data <10 ps (~1.5 mm). Qualcomm interlane match 1.4 mm (up to 2.5 Gb/s). NVIDIA forum: <5 ps clock-to-data at 2.5 Gb/s. — [ADI GMSL2 UG-2212](https://www.analog.com/media/en/technical-documentation/user-guides/public-gmsl2-hardware-design-and-validation-guide.pdf); [Cadence MIPI](https://resources.pcb.cadence.com/blog/2024-mipi-pcb-design-guidelines-for-high-speed-interfaces-cadence); [Renesas](https://www.renesas.com/en/document/apn/pcb-design-guidelines-mipi-csi-mipi-dsi-usb20-and-pci-express-gen2); [Toradex](https://docs.toradex.com/102492-layout-design-guide.pdf); [Qualcomm CSI](https://docs.qualcomm.com/bundle/publicresource/topics/80-PV086-5P/mipi-csi-d-phy-routing-constraints-up-to-2dot5-Gbps.html); [Qualcomm DSI](https://docs.qualcomm.com/doc/80-PV086-5P/topic/mipi-dsi-dphy-routing-constraints.html); [NVIDIA forum](https://forums.developer.nvidia.com/t/mipi-csi-2-clock-data-skew/65031)

#### DDR3 / DDR4 / LPDDR4
- TI: fly-by required for DDR4; balanced-T (used for DDR2) not supported. ADDR_CTRL net class length-matched to the CK net class at each SDRAM. Stubs at each SDRAM short and approximately equal. Length matching only within a byte lane; matching across bytes "neither required nor recommended." DQ/DM routed along the same path as their DQS pair. Route each data group on one layer with the same via count and via barrel length. Numeric limits are in TI's "Data Group Routing Limits" tables (for example Table 10 in SPRACI2A, Table 2-7 in SPRAD06C). — [TI SPRACU1 AM64x DDR](https://www.ti.com/lit/pdf/spracu1); [TI SPRACI2](https://www.ti.com/lit/pdf/spraci2); [TI SPRAD06](https://www.ti.com/lit/pdf/sprad06)
- NXP AN5097: fly-by for address, command, control and clock. In fly-by, the clock trace must be at least as long as the relevant byte-lane strobe (for write leveling; paraphrased from snippet). — [NXP AN5097](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/imx-processors/188384/1/AN5097.pdf)
- TI LPDDR4 (Jacinto7): CK intra-pair skew ≤**0.75 ps**; propagation delay of CK and CMD_ADDR/CTRL net classes ≤**300 ps**. CK and ADDR_CTRL are point-to-point. AM62x: target skew in layout <**20 % of the limit**. — [TI SPRACN9](https://www.ti.com/lit/pdf/spracn9); [TI SPRAD66](https://www.ti.com/lit/pdf/sprad66)
- Vendor examples (not interchangeable): Synaptics SL2610 DDR4: DQ–DQS ±70 ps, DQ–DQ within byte ±40 ps, DQSp–DQSn ±0.5 ps. Efinix LPDDR4 at 3700 Mb/s: DQ–DQS max 75 ps, CK–DQS max 350 ps, CK–address 100 ps. Xilinx UG583: ±5 ps DQ-to-DQS window for an LPDDR4 case. — [Synaptics SL2610](https://cp.synaptics.com/cognidox/download/NR-159702-AN-APPROVED.pdf); [Efinix DDR guide](https://www.efinixinc.com/docs/pcb-guidelines-ddr-ti-ug-v1.2.pdf); [Xilinx UG583](https://web.pa.msu.edu/people/edmunds/Disco_Kraken/Memory_Design/xilinx_ug583_ultrascale_pcb_design.pdf)

#### SPI / QSPI at high clock rates
- Infineon (133 MHz quad-SPI flash): IO[0:3] matched ±**30 mil**; SCK to IO ±**200 mil**; SCK to CS# ±**1500 mil**. Matching must include via electrical length. — [Infineon AN240090](https://www.infineon.com/assets/row/public/documents/10/42/infineon-an240090-design-and-layout-guide-for-cyrs17b-cyel17b-flash-quad-devices-applicationnotes-en.pdf)
- Series damping resistor at the driver. RP2040 guide: 0 Ω, or 10–100 Ω if required, on QSPI clock. TI K2G E2E: 0 Ω near the clock output and 10 Ω near the device (as stated in the forum). Forum: termination matters for clocks ≥50 MHz or long busses. Forum users at 80–120 MHz report short, similar-length routing is sufficient. — [PCB Artists RP2040](https://pcbartists.com/design/embedded/rp2040-pcb-design/); [TI E2E K2G QSPI](https://e2e.ti.com/support/processors-group/processors/f/processors-forum/541174/k2g-pcb-guidlines-for-qspi); [EDAboard SPI termination](https://www.edaboard.com/threads/spi-termination-resistor.365787/); [EEVblog QSPI 120 MHz](https://www.eevblog.com/forum/projects/routing-qspi-flash-memory-to-work-120mhz/)

#### Crystals and oscillators
- ST AN2867: crystal "as close as possible to the microcontroller" with short tracks. A ground-connected guard ring around crystal connections is "essential." Use a local ground plane on the layer immediately below the guard ring, needed only near the crystal. Tie the oscillator ground to the nearest MCU ground. Do not ground a metal-can crystal to the oscillator ground. Keep load capacitors symmetric. Avoid stray capacitance and inductance, which can cause startup problems or unwanted oscillation modes. Coat the board in humid environments (leakage). — [ST AN2867](https://www.st.com/resource/en/application_note/an2867-guidelines-for-oscillator-design-on-stm8afals-and-stm32-mcusmpus-stmicroelectronics.pdf); [AN2867 Rev 15 mirror](https://www.ecsxtal.com/store/pdf/stm32-microcontroller-application-note-092823.pdf)

#### Default interface constraint table (starting values; override with the vendor guide)
| Interface | Zdiff / Zse | Intra-pair skew | Inter-pair / group | Vias | In-line parts and placement | Source |
|---|---|---|---|---|---|---|
| USB 2.0 HS | 90 Ω ±15% / 45 Ω | ≤50 mil (1.27 mm) | n/a | ≤4 per trace (TI) | ESD close to connector; solid GND under DP/DM | [TI SLLA414](https://www.ti.com/lit/pdf/slla414); [Microchip](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf) |
| USB 3.x SS | 90 Ω (some docs: 100 Ω ±10%) | ≤5 mil (0.127 mm) | ≥5 W pair-to-pair | ≤2 per trace | TX AC caps 0402, symmetric, near connector | [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7); [TI SLLA414](https://www.ti.com/lit/pdf/slla414) |
| PCIe Gen3+ | 85 Ω ±15% (CEM, secondary) | ≤5 mil | ≥5 W | minimise; stub <15 mil | AC caps on TX side, 0402 | [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7); [PCBSync](https://pcbsync.com/pcie-pcb-layout/) |
| HDMI / DP | 100 Ω | ≤5 mil | ±5 mil inter-pair (ADI) | minimise | ESD near connector | [ADI UG-2212](https://www.analog.com/media/en/technical-documentation/user-guides/public-gmsl2-hardware-design-and-validation-guide.pdf); [NXP AN10798](https://www.nxp.com/docs/en/application-note/AN10798.pdf) |
| MIPI D-PHY | 100 Ω ±10–20% (some 90 Ω) | ≤5 mil or <1 ps | clk–data <5–10 ps; ~1.4 mm interlane | minimise | none | [Toradex](https://docs.toradex.com/102492-layout-design-guide.pdf); [Qualcomm](https://docs.qualcomm.com/bundle/publicresource/topics/80-PV086-5P/mipi-csi-d-phy-routing-constraints-up-to-2dot5-Gbps.html) |
| Ethernet MDI | 100 Ω | match within pair | pairs separated | minimise | PHY↔magnetics ≥25 mm; magnetics near RJ45; Bob Smith to chassis | [Pulse](https://www.mouser.com/pdfDocs/pulse_layout_considerations_final.pdf) |
| DDR4 / LPDDR4 | vendor (often 40–50 Ω SE, 80–100 Ω diff) | DQS/CK pair: ≤0.5–0.75 ps | DQ↔DQS within byte only; ADDR/CMD↔CK at each DRAM | equal via count per byte group | fly-by; same layer per byte | [TI SPRACU1](https://www.ti.com/lit/pdf/spracu1); [TI SPRACN9](https://www.ti.com/lit/pdf/spracn9) |
| QSPI 133 MHz | SE ~50 Ω | n/a | IO ±30 mil; SCK–IO ±200 mil; SCK–CS ±1500 mil | count in length | series R at driver | [Infineon AN240090](https://www.infineon.com/assets/row/public/documents/10/42/infineon-an240090-design-and-layout-guide-for-cyrs17b-cyel17b-flash-quad-devices-applicationnotes-en.pdf) |
| Crystal | n/a | n/a | n/a | avoid | ≤ few mm from MCU; guard ring; local GND below | [ST AN2867](https://www.st.com/resource/en/application_note/an2867-guidelines-for-oscillator-design-on-stm8afals-and-stm32-mcusmpus-stmicroelectronics.pdf) |

### Inferences
- DDR "40–50 Ω SE, 80–100 Ω diff" in the table is a placeholder range, not a sourced value. Always read the controller guide. DDR limits are expressed in ps by TI and Efinix, so the generator should support delay-based constraints (ps → mm via per-layer propagation velocity) rather than fixed mm.
- The USB SuperSpeed AC caps ("near connector", per TI and JLCPCB) and PCIe AC caps ("near TX", per PCBSync) look contradictory but are consistent. On a host board the TX is the local PHY output, and the caps sit somewhere on that TX path. The connector-proximity advice applies when the connector is the channel's far end. Treat placement as "on the TX leg, symmetric, as specified by the PHY vendor."

### Gaps
- Primary USB-IF, PCI-SIG (CEM), HDMI Forum and MIPI Alliance layout documents were not retrievable. All interface numbers above come from vendor application notes.
- No DDR3-specific numeric tables were retrieved. TI's DDR4 data-group tables were referenced but not reproduced in the snippets.
- No primary source was found on the placement of a series resistor relative to a TVS, or on the clock-length convention for QSPI (the RP2040 guide says the clock should be the longest, which conflicts with flight-time matching).

---

## 5. Termination, stubs, via stubs/backdrilling, and when a trace is electrically long

### Takeaway
A trace needs transmission-line treatment (controlled Z, termination, stub control) when its delay is a significant fraction of the signal rise time, not the clock period. The commonly used threshold is a one-way delay above roughly tr/6 to tr/2 depending on the source. Altium and others argue that the real criterion depends on source and load impedance mismatch. Via and branch stubs resonate at the quarter wave, about f ≈ 1.5 GHz/len[in] in FR-4. Bogatin's conservative design rule is stub length [in] < 0.3 / data rate [Gb/s]; backdrill when that is exceeded.

### Cited Findings
- Bandwidth from rise time: BW ≈ 0.35/RT (Bogatin Rule of Thumb #1). Johnson and Graham's knee frequency f_knee = 0.5/t_r. These are two constants answering different questions (−3 dB bandwidth versus maximum significant frequency). — [EDN Rule of Thumb #1](https://www.edn.com/rule-of-thumb-1-bandwidth-of-a-signal-from-its-rise-time/); [rftools 0.35 or 0.5](https://rftools.io/blog/rise-time-knee-frequency/); [Keysight bandwidth reprint](https://www.keysight.com/content/dam/keysight/en/doc/ungate/article-reprints/Understanding-bandwidth-requirements.pdf)
- ADI MT-097: terminate when the one-way delay exceeds **½ of the rise/fall time**. A more conservative rule allows **2 inches of track per ns** of rise time. — [ADI MT-097](https://www.analog.com/media/en/training-seminars/tutorials/mt-097.pdf)
- The most-cited definition of critical length is where round-trip delay equals rise time. Practitioners quote fractions of 1/2, 1/3, 1/4, 1/5, 1/6, 1/8, 1/10, 1/12 and 1/20 of the rise time. Altium calls the rule "over-communicated and misunderstood," because the real criterion is the input impedance looking into the line, which depends on line length and on the mismatch between Z0 and the load. Johnson notes that the need for termination also depends on driver impedance, load impedance and how clean the signal must be. — [Altium: Stop quoting critical length](https://resources.altium.com/p/can-we-all-stop-quoting-critical-length-rule); [Interference Technology](https://interferencetechnology.com/stop-using-the-critical-length-rule-in-high-speed-pcb-design/); [Johnson, "Line Length"](https://www.sigcon.com/Pubs/news/3_14.htm)
- Hartley: problems track rise time, not clock frequency. — [Proto Express/Hartley](https://www.protoexpress.com/blog/rick-hartley-pcb-design-recommendations-to-minimize-emi/)
- Quarter-wave stub resonance in FR-4: f[GHz] ≈ 1.5/Len[in] ≈ 3.8/Len[cm] (Bogatin Rule #17); a 0.5 in stub resonates near 3 GHz. Design rule: keep stubs < **0.3/Gb/s** inches (10× margin over the older 3/Gb/s quarter-wave estimate). — [EDN Rule of Thumb #17](https://www.edn.com/the-quarter-wave-stub-frequency-rule-of-thumb-17/); [SIJ Fixing the Problem of Stubs](https://www.signalintegrityjournal.com/articles/2962-fixing-the-problem-of-stubs); [PCBSync backdrill](https://pcbsync.com/pcb-back-drilling/)
- TI: via stubs **<15 mil**; longer stubs must be backdrilled. Practical backdrill thresholds are roughly above 5–10 Gb/s, with review from about 2.5–3 Gb/s, and residual stubs of ≤0.2 mm or ≤10 mil (vendor). — [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7); [JLCPCB transitions](https://jlcpcb.com/blog/pcb-signal-transitions); [Advanced PCB backdrill](https://www.advancedpcb.com/en-us/resources/blog/understanding-back-drilling-in-pcb-manufacturing/)
- DDR fly-by: stubs at each DRAM must be short and approximately equal to manage reflections. — [TI SPRACU1](https://www.ti.com/lit/pdf/spracu1)
- Series termination is placed close to the driver output. — [EDAboard SPI termination](https://www.edaboard.com/threads/spi-termination-resistor.365787/)

#### Rule table
| ID | Rule | Numeric | Why | Applies when | Sev | Check | Source |
|---|---|---|---|---|---|---|---|
| TL-1 | Classify a net as electrically long when its one-way delay exceeds a fraction of tr | tr/2 (ADI) down to tr/6 (conservative); 2 in per ns of tr | Reflections become visible when round-trip delay is comparable to tr | All digital nets with known tr | P1 | G: length × per-layer velocity versus tr from the part library | [ADI MT-097](https://www.analog.com/media/en/training-seminars/tutorials/mt-097.pdf); [Altium](https://resources.altium.com/p/can-we-all-stop-quoting-critical-length-rule) |
| TL-2 | Series-terminate point-to-point CMOS drivers on long nets, with the resistor at the driver | Rs + Rdriver ≈ Z0; typical 22–33 Ω (blog) | Source-matched line absorbs the reflection | Electrically long SE clocks and strobes | P1 | G: resistor in series within X mm of the driver pin | [EDAboard](https://www.edaboard.com/threads/spi-termination-resistor.365787/); [Zbotic](https://zbotic.in/i2c-vs-spi-vs-uart-on-pcb-layout-routing-best-practices/) |
| TL-3 | Via stub length | <15 mil (TI); < 0.3/Gb/s in (Bogatin) | Quarter-wave stub resonance creates an insertion-loss notch | SerDes ≥ ~3–5 Gb/s | P0 | G: from stackup and layer pair, compute stub = via span − used span | [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7); [EDN #17](https://www.edn.com/the-quarter-wave-stub-frequency-rule-of-thumb-17/) |
| TL-4 | Avoid T-branches and stubs on high-speed nets; DDR fly-by stubs short and equal | Stub delay ≪ tr | Stub reflections | High-speed nets | P1 | K/G: count of track endpoints and branch detection; stub length | [TI SPRACU1](https://www.ti.com/lit/pdf/spracu1) |
| TL-5 | Keep test points and SMDs off SerDes traces unless required | 0402 max preferred | Pad capacitance discontinuity | SerDes | P1 | G | [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7) |

### Inferences
- A stub checker can be fully automatic in KiCad. Each via's start and end layers are known, the stackup gives layer depths, and the layers actually connected by tracks give the used span. The difference is the stub. Flag when stub > min(15 mil, 0.3/Gbps in). Blind and buried vias or backdrill notes then become the remedy.
- A critical-length classifier needs a rise time per driver. In the absence of IBIS data, an LLM can estimate tr from the part family (for example 1–2 ns for MCU GPIO, under 100 ps for SerDes). That estimate is an assumption that should be flagged to the user.

### Gaps
- No authoritative source was retrieved for parallel (Thevenin/AC) termination component placement rules. Only series termination at the driver was confirmed.
- The attribution of the specific "1/6 of rise time" threshold to a named author could not be confirmed. It appears in Altium's list of quoted fractions.

---

## 6. Crosstalk: spacing, parallel-run limits, orthogonal adjacent layers, guard traces

### Takeaway
For 50 Ω lines in FR-4, an edge-to-edge spacing of about 2× line width gives roughly 2.5% NEXT per aggressor, which keeps worst-case bus NEXT under 5% (Bogatin). The 3W rule is a conservative heuristic that ignores dielectric height. Crosstalk scales with spacing relative to height above the plane, so lowering the height (thinner dielectric) is as powerful as adding spacing. Microstrip far-end crosstalk grows with coupled length and inversely with rise time. Guard traces help only when properly stitched and only at extreme isolation targets; extra spacing is usually better.

### Cited Findings
- Bogatin Rule of Thumb #20: for 50 Ω lines in FR-4, spacing ≈ **2× line width** gives NEXT ≈ **2.5%** for both microstrip and stripline, keeping worst-case NEXT in SE buses under 5%. Higher Z0 at the same spacing gives more crosstalk. Exact spacing (2× versus 3×) needs a 2D field solver. — [EDN Rule of Thumb #20](https://www.edn.com/how-far-is-far-enough-signal-line-spacing-for-acceptable-near-end-crosstalk-rule-of-thumb-20/)
- Bogatin Rule of Thumb #21: for tightly spaced 50 Ω microstrips in FR-4, FEXT ≈ **0.5% × Len[in] / RT[ns]**; for example 10 in coupled at 1 ns RT gives ≈5%. Closer spacing gives more FEXT. — [EDN Rule of Thumb #21](https://www.edn.com/how-to-engineer-acceptable-far-end-crosstalk-rule-of-thumb-21/)
- Altium: the 3W rule ignores that inductive crosstalk depends on shared loop area. With reduced loop area (closer plane), 1.5W–2W is appropriate in many designs, so run a crosstalk simulation. AtlasPCB proposes a "3H" rule relative to dielectric height (vendor). — [Altium crosstalk](https://resources.altium.com/p/crosstalk-elimination-techniques-in-altium-designer); [AtlasPCB SI guide](https://atlaspcb.com/blog/signal-integrity-pcb-design-guide/)
- Guard traces: a DesignCon 2013 paper (Simonovich) finds guard traces worth considering only when more than **−60 dB** isolation is needed at high density, and in some cases stitching the guard gives no benefit. Microstrip guards give little to no benefit. Floating or end-grounded guards can resonate and increase coupling. Doubling spacing often beats a poorly implemented guard. — [SIJ/DesignCon 2013 Guard Traces paper](https://www.signalintegrityjournal.com/ext/resources/article-images-2019/Guard-Traces---Love-Them-or-Leave-Them/4567Guard_Trace_DesignCon-2013-rev14_Final.pdf?trk=public_post_comment-text); [Lamsim: Are Guard Traces Worth It?](https://blog.lamsimenterprises.com/2013/04/12/are-guard-traces-worth-it/)
- A guard trace that is stitched should have stitch spacing of about λ/10 of the highest frequency (one camp in the debate). — [Lamsim white paper](http://lamsimenterprises.com/Guard_Traces_White_PAPER-iss02.pdf)
- Hubing ("Not-So-Good" guidelines): the rule "one ground return trace per eight signal lines" is too narrow to be a general rule. — [LearnEMC Not-So-Good Guidelines](https://learnemc.com/not-so-good-emc-design-guidelines)
- Ott: analog and digital signals should not cross; if they must, cross at right angles. — [Ott EE Times](https://www.eetimes.com/partitioning-and-layout-of-a-mixed-signal-pcb-3/)
- Bogatin: a wide continuous plane adjacent to the trace is the lowest-crosstalk configuration. — [Bogatin SIJ](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers)
- KU Leuven SI course notes give a 3W rule for microstrip and note that stripline coupling appears for spacing ≥2W (as summarised). — [KU Leuven crosstalk deck](https://iiw.kuleuven.be/onderzoek/remi/projects/DfXBridge/UserDocuments/crosstalk.pdf)

#### Rule table
| ID | Rule | Numeric | Why | Applies when | Sev | Check | Source |
|---|---|---|---|---|---|---|---|
| XT-1 | Minimum edge-to-edge spacing between unrelated high-speed SE nets | ≥2 W (≈2.5% NEXT at 50 Ω, FR-4); 3 W conservative | Mutual C and L fall off with s/h | Fast-edge SE nets | P1 | K: net-class-to-net-class clearance (spacing is in mm, so compute W per layer) | [EDN #20](https://www.edn.com/how-far-is-far-enough-signal-line-spacing-for-acceptable-near-end-crosstalk-rule-of-thumb-20/) |
| XT-2 | Limit coupled parallel length on microstrip | FEXT ≈ 0.5% × Len[in]/RT[ns] at tight spacing; budget, for example, ≤3% | FEXT accumulates with length in inhomogeneous media | Microstrip, fast edges | P1 | G: pairwise parallel-run extraction (segments within distance d on the same layer) | [EDN #21](https://www.edn.com/how-to-engineer-acceptable-far-end-crosstalk-rule-of-thumb-21/) |
| XT-3 | Inter-pair spacing for diff pairs | ≥5 W | Lane-to-lane crosstalk | SerDes | P1 | K | [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7) |
| XT-4 | Cross sensitive and aggressor nets at 90° on adjacent layers; avoid broadside parallel runs | 90° | Minimises coupled length | Dual-stripline, analog/digital | P2 | G: broadside overlap length on adjacent signal layers | [Ott EE Times](https://www.eetimes.com/partitioning-and-layout-of-a-mixed-signal-pcb-3/) |
| XT-5 | Use guard traces only when isolation targets are extreme (> −60 dB) and they can be stitched; otherwise use spacing | Stitch ≤λ/10 | Floating guards resonate | Rare | P2 | G: guard net has vias at pitch ≤ λ/10 and both ends grounded | [DesignCon 2013 paper](https://www.signalintegrityjournal.com/ext/resources/article-images-2019/Guard-Traces---Love-Them-or-Leave-Them/4567Guard_Trace_DesignCon-2013-rev14_Final.pdf?trk=public_post_comment-text) |

### Inferences
- Because crosstalk scales with s/h, the generator should express spacing rules in units of the layer's dielectric height (or of trace width, which is itself set by h at fixed Z0). It should emit per-layer mm values, rather than one global "3W".
- In homogeneous stripline, FEXT nearly cancels, so the parallel-run-length limit matters mainly on outer layers. This is standard theory and consistent with Bogatin's microstrip-specific formula, but it was not explicitly sourced here.

### Gaps
- No primary source for orthogonal routing of adjacent signal layers ("dual stripline") specifically. Only Ott's analog/digital right-angle crossing rule was found.
- Ritchey's crosstalk material (Altium article) was surfaced but not read in detail.

---

## 7. EMI/EMC: edge rates, board edges and connectors, via fencing, I/O grouping, filtering, chassis ground, ESD/TVS, CMCs, shields, slot antennas, ground splitting

### Takeaway
Cables are the dominant antennas. Most board-level EMC wins come from (1) controlling return paths so that no common-mode voltage develops between connectors (keep all I/O on one edge or corner, and keep high-speed circuitry and traces away from I/O and board edges), (2) filtering and protecting at the connector with very short ground connections, and (3) using the slowest edge rate that meets timing. Plane splits and slots become antennas above roughly 100 MHz. Hubing and Ott both argue against splitting ground planes; partition the layout instead.

### Cited Findings
- Hubing: designers "should try to locate all cable connectors on one edge or corner of a PCB." Connectors with attached cables are the most common EMI antenna parts. "Current-driven sources occur when high-speed circuitry is located anywhere between two antenna parts." — [Hubing, PCB EMI Source Mechanisms (EMCS03-001)](https://cecas.clemson.edu/cvel/pdf/EMCS03-001.pdf)
- LearnEMC: all external connections on one board edge keep the plane usable as a reference, as long as high-speed traces stay away from (and do not run parallel to) that edge. If high-speed circuitry must sit between connectors, bond the board to a metal chassis on both sides. — [LearnEMC PCB layout intro](https://learnemc.com/pcb-layout); [LearnEMC Good EMC Guidelines](https://learnemc.com/other-good-emc-design-guidelines)
- Traces near the PCB edge: common-mode current rises as a trace moves closer to the edge. A copper guard band along the ground-plane edge near the trace is the most effective suppression method studied. — [ResearchGate: CM current due to a trace near a PCB edge](https://www.researchgate.net/publication/3056626_Common-Mode_Current_Due_to_a_Trace_Near_a_PCB_Edge_and_Its_Suppression_by_a_Guard_Band)
- Via fencing and stitching: keep spacing < **λ/20** at the highest frequency of concern (FR-4 Dk≈4: ≈7.5 mm at 1 GHz, ≈0.75 mm at 10 GHz). λ/10 is a common compromise. Perimeter stitching at 3–5 mm pitch; ~2 mm around high-speed interfaces (all vendor or secondary). Edge plating shields better than fencing, at higher cost. — [AtlasPCB stitching vias](https://www.atlaspcb.com/blog/pcb-ground-plane-stitching-via/); [Flux via stitching](https://www.flux.ai/p/blog/via-stitching-pcb-guide); [AtlasPCB shielding](https://www.atlaspcb.com/blog/pcb-emi-shielding-via-fencing-board-level-shield/); [USPTO 11096277 edge plating](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11096277)
- Slot antennas and splits: high-frequency lines crossing splits radiate. Above ~100 MHz the slot formed by a split acts as an effective antenna (TPS case study). The TPS fix was stitching vias at **10–15 mm** intervals along the split (the customer had 40–50 mm). An unverified vendor glossary claims a 2 mm slot under a 50 Ω microstrip at 5 GHz raises emissions 10–15 dB. — [TPS EMC case study](https://tps-elektronik.com/en/case-studies/how-to-pass-automotive-conducted-emissions-cispr-25-class-5-with-tps-split-ground-plane-and-common-mode-choke-placement-emc-layout-guidelines-for-automotive-dc-dc-converters/); [ADI AN-1109](https://www.analog.com/en/resources/app-notes/an-1109.html); [RF Essentials glossary](https://rfessentials.com/resources/rf-glossary/ground-plane/); [Clemson EMCS97-159](https://cecas.clemson.edu/cvel/pdf/EMCS97-159.pdf)
- Ground splitting (Ott): use one ground plane and partition the layout into analog and digital sections, with analog routing only in the analog section and digital only in the digital section. ADCs straddle the partition. Splits force return current into large loops, which raises radiation and ground inductance and makes analog circuits susceptible. The digital return follows the same path whether or not the plane is split. — [Ott EE Times](https://www.eetimes.com/partitioning-and-layout-of-a-mixed-signal-pcb-3/); [Ott tech tip](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html)
- TI (SLYT512) presents partitioned, split-plane (with careful current management), multipoint and star grounding as options. — [TI SLYT512](https://www.ti.com/lit/an/slyt512/slyt512.pdf)
- Hubing lists gapping ground planes between analog and digital, and requiring a common-mode choke on every board's power input, among four common EMC myths. His 2019 talk lists "blindly adhering to EMC design guidelines" among the most common layout errors. — [Altium: Four Commonly Held Myths of EMC Design](https://resources.altium.com/p/four-commonly-held-myths-emc-design); [Hubing 2019 IEEE SCV talk](https://r6.ieee.org/scv-emcs/wp-content/uploads/sites/111/022019ToddHubing.pdf)
- ESD/TVS (TI SLVA680): place the TVS as close to the ESD source (connector) as layout allows and the protected IC farther away, so that the inductance from TVS to IC far exceeds the inductance from connector to TVS. Route the protected line directly from the connector to the TVS pin, ideally without vias and with no stub. The TVS-to-ground inductance is the most significant parasitic on clamp voltage. A chassis ground separated from digital ground by inductance gives good ESD protection but is harder to route with high-speed signals. Vendor numbers: TVS within 10 mm (AtlasPCB) or 5 mm (Zbotic) of the connector pin; dedicated ground vias at the TVS ground pad, not shared (NextPCB). — [TI SLVA680](https://www.ti.com/lit/pdf/slva680); [TI excerpt (elecfans)](https://file.elecfans.com/web1/M00/00/04/o4YBAFnLiNSALZeyAAn7jaJhi5M951.pdf); [AtlasPCB ESD](https://www.atlaspcb.com/blog/pcb-esd-protection-tvs-guard-ring-layout/); [NextPCB TVS](https://www.nextpcb.com/blog/tvs-diode-pcb-design-layout-guide)
- Common-mode chokes: place within ~**5 mm** of the connector, because traces between connector and choke act as antennas that bypass the filter. Typical order from the connector inward is ESD → CMC → transceiver (some designs put ESD SoC-side). Do not put Y-caps on the line side of the choke (that bypasses it). A chassis/signal moat bridged only by the CMC and specific caps is one approach (all vendor or secondary). — [NextPCB CMC](https://www.nextpcb.com/blog/common-mode-choke-pcb-layout-guide); [PCBSync CMC](https://pcbsync.com/common-mode-choke/); [NextPCB CMC USB/HDMI/CAN](https://www.nextpcb.com/blog/common-mode-choke-usb-hdmi-can-bus-pcb-layout); [TPS case study](https://tps-elektronik.com/en/case-studies/how-to-pass-automotive-conducted-emissions-cispr-25-class-5-with-tps-split-ground-plane-and-common-mode-choke-placement-emc-layout-guidelines-for-automotive-dc-dc-converters/)
- Shielded connectors: 360° termination of the shield to chassis. — [ConnectorTips: EMI at harness-to-PCB interfaces](https://www.connectortips.com/how-to-manage-emi-at-the-harness-to-pcb-interfaces/)
- Edge rate: faster rise time raises the knee frequency and broadens the harmonic spectrum. Rise time comes from the driver, not the clock. Slowing edges (for example with gate or series resistors) lowers the knee below problem bands. — [EMC Insight frequency knee](https://emcinsight.com/understanding-the-frequency-knee-of-a-signal/); [rftools](https://rftools.io/blog/rise-time-knee-frequency/); [electricalflux](https://electricalflux.com/learn-components/frequency-square-wave-harmonics-circuit-behavior)
- LearnEMC: full ground planes under every component are usually sensible, but can cause problems around some transformers, chokes and power-supply circuits. Fixed decoupling-value rules (0.1 µF to 15 MHz, 0.01 µF above) are too narrow to be general. — [LearnEMC Not-So-Good Guidelines](https://learnemc.com/not-so-good-emc-design-guidelines)
- LearnEMC course notes: "minimize high-speed trace length" does not necessarily fix a real EMC problem; such traces are routinely routed without issue. — [LearnEMC CH11 PCB Layout notes](https://learnemc.com/ext/pdf/EMC-Course-Notes/CH11-Printed-Circuit-Board-Layout.pdf)

#### Rule table
| ID | Rule | Numeric | Why | Applies when | Sev | Check | Source |
|---|---|---|---|---|---|---|---|
| EMI-1 | Place all cable connectors on one edge or corner | none | Avoids CM voltage between two antenna parts | Boards with ≥2 cabled connectors | P1 | G: connector bounding boxes cluster on one edge; score by angular spread | [Hubing EMCS03-001](https://cecas.clemson.edu/cvel/pdf/EMCS03-001.pdf) |
| EMI-2 | No high-speed circuitry between two cabled connectors; keep high-speed traces away from the I/O edge | Keep-out region (designer-set) | Current-driven CM source | Same | P1 | G/K: rule area keepout for high-speed net classes near the I/O edge | [Hubing EMCS03-001](https://cecas.clemson.edu/cvel/pdf/EMCS03-001.pdf); [LearnEMC](https://learnemc.com/pcb-layout) |
| EMI-3 | Keep high-speed traces away from board edges | No standard number; a common heuristic is ≥ several h; guard band of plane copper | CM current rises near the edge | All fast nets | P1 | K: custom `edge_clearance` for high-speed net classes | [ResearchGate edge study](https://www.researchgate.net/publication/3056626_Common-Mode_Current_Due_to_a_Trace_Near_a_PCB_Edge_and_Its_Suppression_by_a_Guard_Band) |
| EMI-4 | Stitch GND planes together with vias at the perimeter and around high-speed areas | ≤λ/20 at fmax (≈7.5 mm at 1 GHz); 3–5 mm perimeter; ~2 mm near SerDes (vendor) | Suppresses plane-pair cavity resonance and edge radiation | Multilayer with ≥2 GND planes | P1 | G: max gap between adjacent GND vias along a polyline offset from the edge | [AtlasPCB](https://www.atlaspcb.com/blog/pcb-ground-plane-stitching-via/) |
| EMI-5 | Do not split ground; partition by function and place ADCs across the partition | none | Splits create loops and slot antennas | Mixed-signal | P1 | G: detect multiple GND-net zones on the same layer with gaps under traces | [Ott EE Times](https://www.eetimes.com/partitioning-and-layout-of-a-mixed-signal-pcb-3/) |
| EMI-6 | If a split or slot exists, stitch or bridge it under every crossing trace | Stitch ≤10–15 mm along the split (TPS case) | Slot antenna above ~100 MHz | Same | P0 | G | [TPS](https://tps-elektronik.com/en/case-studies/how-to-pass-automotive-conducted-emissions-cispr-25-class-5-with-tps-split-ground-plane-and-common-mode-choke-placement-emc-layout-guidelines-for-automotive-dc-dc-converters/) |
| EMI-7 | TVS at the connector, protected line passes through the TVS pad without a stub, short and low-L ground | ≤5–10 mm from connector pin (vendor); dedicated GND via(s) | Steer ESD current before it reaches the IC | All external I/O | P0 | G: distance(TVS pad, connector pin); trace topology order connector→TVS→IC; via at TVS GND pad within ~1 mm | [TI SLVA680](https://www.ti.com/lit/pdf/slva680) |
| EMI-8 | CMC and filters at the connector, before any trace runs inside the board | ≤~5 mm (vendor) | Trace before the filter re-radiates | Cabled I/O | P1 | G | [NextPCB](https://www.nextpcb.com/blog/common-mode-choke-pcb-layout-guide) |
| EMI-9 | Use the slowest edge rate that meets timing; add series R or slew control | knee ≈ 0.5/tr | Spectrum content above the knee is small | All digital | P2 | G: report nets with drive strength or slew settings; schematic-level | [rftools](https://rftools.io/blog/rise-time-knee-frequency/) |
| EMI-10 | Chassis ground region for shielded connectors and Ethernet; bond shields 360° | Bob Smith 75 Ω + ~1000 pF HV | ESD and CM currents kept off signal ground | Shielded I/O | P1 | G | [Microchip](https://ww1.microchip.com/downloads/en/Appnotes/00002054A.pdf); [ConnectorTips](https://www.connectortips.com/how-to-manage-emi-at-the-harness-to-pcb-interfaces/) |

### Inferences
- A useful automated "EMC posture" score: (a) connector clustering, (b) high-speed net length within an I/O-edge buffer zone, (c) high-speed net proximity to the board outline, (d) GND via-fence max gap, (e) TVS and CMC distance to connector pins, and (f) plane-split crossings. All of these are geometric and computable from the KiCad board file.
- One vendor source suggests placing fast devices near connectors, which conflicts with Hubing's framing. Follow Hubing and LearnEMC: keep high-speed circuitry away from and not between I/O, while keeping each interface's PHY-to-connector path short.

### Gaps
- No authoritative numeric "distance of high-speed trace from board edge" was found. Hubing and LearnEMC give the qualitative rule only.
- Shielding-can footprint rules (fence via pitch, can-to-plane bonding) were not found in primary sources. λ/20 stitching applies by analogy.
- No primary source for Y-cap or CMC values or for placement relative to the shield bond was retrieved.

---

## 8. Placement priorities driven by SI/EMI

### Takeaway
Place fixed and mechanically constrained items first (connectors, mounting, keep-outs), clustering cabled connectors on one edge. Next place the parts that "belong" to the connector (ESD, CMC, magnetics, AC caps, filters) immediately at it. Then place the critical ICs (SoC, DDR, PHYs, clocks), oriented so that high-speed paths are short, direct and do not cross each other or the I/O zone. Then partition the remaining circuitry by function and frequency (fast digital, slow digital, analog, power) with one continuous ground, and finally place decoupling and passives.

### Cited Findings
- Connectors on one edge or corner; high-speed circuitry not between antenna parts. — [Hubing EMCS03-001](https://cecas.clemson.edu/cvel/pdf/EMCS03-001.pdf)
- TVS as close as possible to the connector, IC farther away. — [TI SLVA680](https://www.ti.com/lit/pdf/slva680)
- CMC within ~5 mm of the connector. Order connector → ESD → CMC → IC. — [NextPCB](https://www.nextpcb.com/blog/common-mode-choke-pcb-layout-guide); [PCBSync](https://pcbsync.com/common-mode-choke/)
- Ethernet: magnetics near the RJ45, PHY ≥25 mm away from the magnetics. — [Pulse](https://www.mouser.com/pdfDocs/pulse_layout_considerations_final.pdf)
- Crystal as close as possible to the MCU, with a guard ring and local ground. — [ST AN2867](https://www.st.com/resource/en/application_note/an2867-guidelines-for-oscillator-design-on-stm8afals-and-stm32-mcusmpus-stmicroelectronics.pdf)
- Mixed-signal: partition into analog and digital sections over one ground; ADCs straddle the boundary; analog signals routed only in the analog section. — [Ott EE Times](https://www.eetimes.com/partitioning-and-layout-of-a-mixed-signal-pcb-3/)
- DDR: fly-by topology determines DRAM placement (chain from controller); route each byte group on one layer with equal via counts. — [TI SPRACU1](https://www.ti.com/lit/pdf/spracu1); [NXP AN5097](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/imx-processors/188384/1/AN5097.pdf)
- USB SS: AC caps, CM filter and ESD as short and close to the connector as possible. — [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7)
- A vendor design guide recommends partitioning by logic speed: fast devices and clock sources near connectors, slow logic and memory away. This conflicts with Hubing and is noted as a disagreement. — [allPCB EMC guidelines](https://www.allpcb.com/allelectrohub/emc-design-guidelines-for-digital-circuits)

#### Placement priority order (machine-actionable)
| Step | Action | Rule source |
|---|---|---|
| 1 | Lock mechanical items: board outline, mounting holes, connectors (cabled connectors grouped on one edge or corner), switches, displays | [Hubing](https://cecas.clemson.edu/cvel/pdf/EMCS03-001.pdf) |
| 2 | Place connector-attached protection and filtering: TVS/ESD, CMC, magnetics, Bob Smith network, shield/chassis bond, at distances per §7 | [TI SLVA680](https://www.ti.com/lit/pdf/slva680); [Pulse](https://www.mouser.com/pdfDocs/pulse_layout_considerations_final.pdf) |
| 3 | Place critical ICs (SoC/FPGA, DRAM in fly-by order, PHYs, SerDes redrivers), oriented so pin escape faces its peer and high-speed paths are short and uncrossed | [TI SPRACU1](https://www.ti.com/lit/pdf/spracu1) |
| 4 | Place clock sources (crystal or oscillator) next to their consumer; keep away from I/O edge and board edges | [ST AN2867](https://www.st.com/resource/en/application_note/an2867-guidelines-for-oscillator-design-on-stm8afals-and-stm32-mcusmpus-stmicroelectronics.pdf); [LearnEMC](https://learnemc.com/pcb-layout) |
| 5 | Partition the rest by function and frequency (analog / fast digital / slow digital / power) over continuous ground; ADCs straddle the partition | [Ott](https://www.eetimes.com/partitioning-and-layout-of-a-mixed-signal-pcb-3/) |
| 6 | Place in-line SI parts (series R at driver, AC caps symmetric on TX leg) | [EDAboard](https://www.edaboard.com/threads/spi-termination-resistor.365787/); [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7) |
| 7 | Decoupling and remaining passives (PI rules are outside this note's scope) | n/a |

### Inferences
- Steps 1–3 can be encoded as hard placement constraints, as anchor-relative distance limits (for example TVS within 5–10 mm of connector pin N). Steps 4–6 can be encoded as soft objectives in a placer cost function. The cost terms are high-speed net length, crossings, I/O-zone intrusion and distance to edge.

### Gaps
- No single primary source prescribing the full placement order was retrieved. The order above is synthesised from the individual rules cited.

---

## 9. Myths and context-dependent rules of thumb

### Takeaway
Several famous rules are either wrong in general or only valid in a narrow context. The 20H rule increases far-field radiation slightly in measurements. 90° corners are irrelevant below tens of GHz. Ground-plane splitting usually hurts. 3W is an over-conservative stand-in for s/h. Guard traces often do nothing or harm. Critical length is a simplification of an impedance-mismatch problem. "Minimise trace length" and "CMC on every input" are not universal. An LLM rule engine should encode the physics behind these rules and avoid applying them blindly.

### Cited Findings
| Rule | Verdict | Evidence | Source |
|---|---|---|---|
| 20H rule (pull the power plane back 20× the plane spacing) | Myth for radiation reduction. It contains near fields, but measured far-field radiation is slightly higher (3.6 dB higher at the TM10 mode in one summary) | Hubing and Shim measurements; Altium reports similar results | [Shim & Hubing, 20-H Rule Modeling and Measurements](https://cecas.clemson.edu/cvel/pdf/EMCS01-939.pdf); [Scholars' Mine](https://scholarsmine.mst.edu/ele_comeng_facwork/1333/); [Altium: How fast is fast](https://resources.altium.com/p/high-speed-pcb-design-just-how-fast-is-fast) |
| 90° corners | Myth for digital. Johnson: bends perform fine in digital designs up to 2 Gb/s; the corner is too small to affect far-field radiation. Altium simulation: about 3 Ω (3%) deviation on a 100 Ω pair up to roughly 80 GHz; a 20 mil trace corner gives no 10% deviation until 60 GHz. The myth traces to Motorola's 1971 MECL handbook figure | Johnson EDN 2000; Altium simulations | [Johnson, "Who's Afraid of the Big Bad Bend?"](https://www.sigcon.com/Pubs/edn/bigbadbend.htm); [Altium: Slaying the 90° dragon](https://resources.altium.com/p/slaying-900-right-angle-bend-dragon); [Altium: routing angle myths](https://resources.altium.com/p/pcb-routing-angle-myths-45-degree-angle-versus-90-degree-angle) |
| Split analog/digital ground planes | Usually harmful. Use one plane and partition the layout; bridge if a split is mandatory | Ott; Hubing lists it as a myth | [Ott EE Times](https://www.eetimes.com/partitioning-and-layout-of-a-mixed-signal-pcb-3/); [Altium: Four myths](https://resources.altium.com/p/four-commonly-held-myths-emc-design) |
| 3W rule | Context-dependent. Crosstalk depends on s/h and loop area; 2W gives about 2.5% NEXT at 50 Ω; 1.5–2W is often fine with a close plane | Bogatin; Altium | [EDN #20](https://www.edn.com/how-far-is-far-enough-signal-line-spacing-for-acceptable-near-end-crosstalk-rule-of-thumb-20/); [Altium crosstalk](https://resources.altium.com/p/crosstalk-elimination-techniques-in-altium-designer) |
| Guard traces | Context-dependent. Useful only at > −60 dB isolation, stitched; little benefit in microstrip; floating or end-only grounded guards can resonate | Simonovich DesignCon 2013 | [DesignCon 2013 paper](https://www.signalintegrityjournal.com/ext/resources/article-images-2019/Guard-Traces---Love-Them-or-Leave-Them/4567Guard_Trace_DesignCon-2013-rev14_Final.pdf?trk=public_post_comment-text) |
| Critical length (fixed fraction of tr) | Simplification. The real issue is input impedance versus mismatch and driver/load impedance; quoted fractions range from 1/2 to 1/20 | Altium; Johnson | [Altium](https://resources.altium.com/p/can-we-all-stop-quoting-critical-length-rule); [Johnson Line Length](https://www.sigcon.com/Pubs/news/3_14.htm) |
| "Minimise all high-speed trace lengths" for EMC | Not necessarily effective. Long high-speed traces are routinely routed without EMC issues when return paths are good | LearnEMC course notes | [LearnEMC CH11](https://learnemc.com/ext/pdf/EMC-Course-Notes/CH11-Printed-Circuit-Board-Layout.pdf) |
| CMC on every power input | Myth (Hubing's four myths) | Hubing podcast summary | [Altium: Four myths](https://resources.altium.com/p/four-commonly-held-myths-emc-design) |
| One ground trace per 8 signal lines; fixed 0.1 µF / 0.01 µF decoupling by frequency | Too narrow to be general rules | Hubing | [LearnEMC Not-So-Good](https://learnemc.com/not-so-good-emc-design-guidelines) |
| A single "best" stackup | No single recipe fits more than a small subset | Hubing | [LearnEMC Not-So-Good](https://learnemc.com/not-so-good-emc-design-guidelines) |
| Following EMC checklists blindly | Hubing: some of the worst designs come from engineers complying with guideline lists | Hubing paper and talk | [Hubing, PCB EMC Design Guidelines: A Brief Annotated List](https://scholarsmine.mst.edu/faculty_work/1672/); [Hubing 2019 talk](https://r6.ieee.org/scv-emcs/wp-content/uploads/sites/111/022019ToddHubing.pdf) |

### Inferences
- Even though 90° corners are harmless electrically below tens of GHz, 45° or arc routing is still a reasonable default for manufacturability and aesthetics, and some vendor guides (older TI USB) still require it. The generator should treat it as P2 (style), not as an SI rule, unless a vendor guide mandates it.
- The 20H rule should not be emitted as a constraint. Plane pull-back for other reasons (manufacturing copper-to-edge clearance) is separate.

### Gaps
- Archambeault's published position on the 20H rule was not retrieved, and Johnson's later comments on bends were not located.

---

## 10. Authoritative sources and their key claims

### Takeaway
The canonical voices converge on the same physics: fields in the dielectric, return paths and loop inductance. They differ in emphasis. Bogatin gives quantitative rules of thumb; Ott gives stackup and grounding doctrine; Hubing gives EMC mechanisms and myth-busting; Johnson debunks bends and frames critical length; Hartley explains energy flow in fields. Vendor application notes (TI, NXP, Microchip, ADI, ST, Infineon, Intel) supply interface-specific numbers.

### Cited Findings
- **Eric Bogatin**: continuous adjacent return path for every signal (20 Rules). BW = 0.35/RT (#1). Stub resonance ≈1.5 GHz/in and stub < 0.3/Gbps (#17). NEXT ≈2.5% at 2W spacing (#20). FEXT ≈0.5% × Len/RT (#21). Wide continuous plane gives lowest crosstalk. — [SIJ 20 Rules](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers); [EDN #1](https://www.edn.com/rule-of-thumb-1-bandwidth-of-a-signal-from-its-rise-time/); [EDN #17](https://www.edn.com/the-quarter-wave-stub-frequency-rule-of-thumb-17/); [EDN #20](https://www.edn.com/how-far-is-far-enough-signal-line-spacing-for-acceptable-near-end-crosstalk-rule-of-thumb-20/); [EDN #21](https://www.edn.com/how-to-engineer-acceptable-far-end-crosstalk-rule-of-thumb-21/)
- **Henry Ott**: five stackup objectives; 4-layer S-to-plane <0.010" with core >0.040"; single ground plane with partitioned layout; bridge splits; ADCs straddle. — [Ott Stack-Up Part 1](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-1.html); [Ott EE Times](https://www.eetimes.com/partitioning-and-layout-of-a-mixed-signal-pcb-3/)
- **Todd Hubing (LearnEMC, Clemson)**: connectors on one edge or corner; current-driven and voltage-driven EMI source mechanisms; 20H rule increases radiation slightly; myths list; guidelines can backfire. — [Hubing EMCS03-001](https://cecas.clemson.edu/cvel/pdf/EMCS03-001.pdf); [20-H Rule paper](https://cecas.clemson.edu/cvel/pdf/EMCS01-939.pdf); [LearnEMC Not-So-Good](https://learnemc.com/not-so-good-emc-design-guidelines)
- **Howard Johnson**: right-angle bends fine to 2 Gb/s; f_knee = 0.5/tr; the line-length and termination decision depends on driver and load impedances. — [Big Bad Bend](https://www.sigcon.com/Pubs/edn/bigbadbend.htm); [rftools on Johnson & Graham](https://rftools.io/blog/rise-time-knee-frequency/); [Line Length](https://www.sigcon.com/Pubs/news/3_14.htm)
- **Rick Hartley**: energy travels in fields in the dielectric; signal plus return form a waveguide; plane must be adjacent; rise time, not clock, matters. — [EEJournal](https://www.eejournal.com/article/matters-of-integrity/); [Altium/Hartley](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley)
- **Lee Ritchey**: an Altium article on crosstalk containment exists; no specific claims were retrievable. — [Altium/Ritchey crosstalk](https://resources.altium.com/p/noise-transfer-annoying-learn-how-contain-crosstalk)
- **TI SPRAAR7**: 5W inter-pair; 5 mil skew (USB3/PCIe/SATA); 1.5W from voids; stitching vias within 200 mil; via stubs <15 mil; AC caps 0402 symmetric; USB3 ≤2 vias. — [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7)
- **TI SLVA680**: ESD layout. **TI SPRACU1/SPRACI2/SPRAD06/SPRACN9/SPRAD66**: DDR4/LPDDR4. **ST AN2867**: oscillators. **Pulse/Microchip**: Ethernet magnetics. **ADI UG-2212**: GMSL2/CSI/HDMI and AC-cap cutouts. **Infineon AN240090**: QSPI. — links in §4 and §7.

### Inferences
- For a knowledge base, tag every rule with (author/source, type ∈ {physics law, rule of thumb, vendor requirement, spec requirement}, confidence). Spec and vendor requirements override rules of thumb, and physics rules generate the checks.

### Gaps
- Primary texts (Ott *EMC Engineering*, Johnson *High-Speed Digital Design*, Bogatin *Signal and Power Integrity Simplified*, Ritchey *Right the First Time*) are books that could not be accessed. Their claims here come from the authors' articles and from secondary summaries.

---

## 11. Which rules are KiCad-encodable versus needing geometric/physics checks

### Takeaway
KiCad's custom rules (`.kicad_dru`) and net classes natively cover widths, clearances, diff-pair gap and uncoupled length, skew (including within diff pairs), via count, hole and edge clearances, and area-scoped rules. They do not cover return-path continuity, reference-plane changes and stitching proximity, loop area, stub length from the stackup, crosstalk coupled length, connector clustering, or "component X within d of connector pin Y" topological placement rules. Those need external geometric checkers that read the board file (for example via the KiCad Python or IPC API).

### Cited Findings
- Rule syntax: `(rule <name> [(severity <severity>)] [(layer <layer_name>)] [(condition <expression>)] (constraint <constraint_type> [constraint_arguments]))`. Values are specified as `(min <value>)`, `(opt <value>)` and `(max <value>)`. — [KiCad 6.0 PCB Editor docs](https://docs.kicad.org/6.0/en/pcbnew/pcbnew.html); [KiCad 9.0 docs](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html)
- `via_count` (max): counts vias on every net matched by the condition and errors when the count exceeds max. — [KiCad 6.0 docs](https://docs.kicad.org/6.0/en/pcbnew/pcbnew.html)
- `diff_pair_uncoupled` (max): maximum uncoupled length where a pair fans out or detours. `skew` (min/opt/max): checks total skew for the matched nets against the group average. — [KiCad 8.0 docs](https://docs.kicad.org/8.0/en/pcbnew/pcbnew.html)
- A forum rule set for a 100 Ω class uses `diff_pair_gap`, `diff_pair_uncoupled (max 3.0mm)` and `skew (min -2ps) (opt 0ps) (max 2ps) (within_diff_pairs)`, scoped by a net-class condition. The forum thread reports confusion over "uncoupled" semantics. — [KiCad forum: How do the diff_pair_* constraints work?](https://forum.kicad.info/t/how-do-the-diff-pair-constraints-work/69785)
- Walkthroughs use a ±5 mil `skew` window for P/N matching. — [Proto Express: diff pairs in KiCad](https://www.protoexpress.com/blog/how-to-route-differential-pairs-in-kicad/); [Tech Explorations: KiCad 9 diff pair tuning](https://techexplorations.com/guides/kicad/high-speed-pcb-design/kicad-9-differential-pair-length-tuning-guide/)
- `edge_clearance` (min/opt/max; a negative min allows overlap); `hole_clearance` (min); `hole_size` (min/max) (KiCad 9). `hole_to_hole` and `track_width` appear in KiCad 6.0 examples. Condition syntax changed from `A.NetClass == 'HV'` (6.0) to `A.hasNetclass('HV')` (9.0). — [KiCad 9.0 docs](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html); [KiCad 6.0 docs](https://docs.kicad.org/6.0/en/pcbnew/pcbnew.html)
- KiCad 10 docs reference "From-To signal path matching" (per search summary). — [KiCad 10.0 docs](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html)
- Users report incomplete integration of custom rules into the interactive router (that is, the router may not honour all custom rules during routing). — [KiCad forum: Incomplete integration of custom rules into router](https://forum.kicad.info/t/incomplete-integration-of-custom-design-rules-into-interactive-router/44396)
- A third-party open-source project (rjwalters/kicad-tools) is building "protocol-aware pair rules" emitting KiCad-native `diff_pair_gap`, `uncoupled`, `skew` and `via_count`, plus its own uncoupled-length checks: relevant prior art for an LLM-driven generator. — [kicad-tools issue #6443](https://github.com/rjwalters/kicad-tools/issues/6443); [kicad-tools epic #6441](https://github.com/rjwalters/kicad-tools/issues/6441); [PR #6556](https://github.com/rjwalters/kicad-tools/pull/6556)
- Community rule examples (fab-specific DRC sets, courtyard rules) exist as templates. — [KiCad forum: custom rules examples](https://forum.kicad.info/t/custom-design-rules-examples/43987); [JLCPCB rules gist](https://gist.github.com/darkxst/f713268e5469645425eed40115fb8b49); [maskset.net custom DRC](https://www.maskset.net/blog/2023/10/30/kicad-custom-drc-rules/)

#### Encodability matrix
| Rule family | KiCad-native (K) | Notes / encoding | Needs external (G/S) |
|---|---|---|---|
| Impedance width/gap per layer | K | Net class diff width/gap; `track_width` and `diff_pair_gap` with `(layer …)` | S: field solver to derive values |
| Intra-pair skew | K | `skew … (within_diff_pairs)`; ps units seen in the forum example | n/a |
| Group length matching (DDR byte lanes, QSPI) | K (partly) | `skew` over a condition matching the group; `length` (see Gaps) | G: delay-aware matching including vias and per-layer velocity if KiCad version lacks it |
| Uncoupled length | K | `diff_pair_uncoupled (max …)` | n/a |
| Via count | K | `via_count (max …)` | n/a |
| Inter-pair / class-to-class spacing (5W, 2–3W) | K | `clearance` with condition on both A and B net classes | n/a |
| Edge keep-off for high-speed nets | K | `edge_clearance` with net-class condition | n/a |
| Keep high-speed nets out of I/O zone | K | Rule area or keepout plus area-conditional rule | G: zone generation |
| Return-path continuity (no split or void crossing, 1.5W from void) | none | n/a | G: segment-over-copper test on the adjacent reference layer |
| Reference change → stitching via or cap proximity | none | n/a | G |
| Loop area / via-to-return-via distance | none | n/a | G |
| Via stub length | none | n/a | G: stackup and via span |
| Crosstalk coupled length (FEXT budget) | none | n/a | G/S |
| TVS/CMC/AC cap distance to connector and order | none | n/a | G: placement and topology check |
| Connector clustering on one edge | none | n/a | G |
| GND via fence pitch | none | n/a | G |
| Serpentine near mismatch | none | n/a | G |
| Crystal proximity and guard ring | none | n/a | G |

### Inferences
- The natural architecture is: LLM classifies nets and components, then emits (a) net classes plus `.kicad_dru` (K rules) and (b) a JSON spec for an external checker suite (G rules). Both are produced from one interface rule table (§4 and §12).
- Because the interactive router may not enforce every custom rule, generated routes must be re-verified with DRC plus the G checks after routing.

### Gaps
- Not verified in this session (fetch blocked), but believed from prior knowledge of KiCad 7–9 docs: a `length (min/max)` constraint exists; condition functions `A.inDiffPair('<pattern>')`, `A.intersectsArea('<zone>')`, `A.enclosedByArea()`, `A.isPlated()`, `A.Type`, `A.Layer` and `A.hasNetclass()` exist; KiCad recognises diff pairs by net-name suffixes `+`/`-` or `P`/`N`; time-domain (ps) length and skew tuning arrived in recent KiCad (the forum example uses ps). **Verify against https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html before encoding.**
- Whether `skew` measures pad-to-pad including via length, and whether it supports per-layer propagation velocity, was not verified.

---

## 12. Implications for an LLM-driven KiCad placer/router

### Takeaway
Build the system around one interface rule table (rows like §4, each carrying impedance, skew, via count, spacing, in-line part placement and a source tag), plus a net and component classifier that maps schematic nets onto those rows. From the table, emit (1) KiCad net classes and a `.kicad_dru` file for everything KiCad can check natively, and (2) a set of external geometric checks for return path, stubs, EMC posture and placement topology, which KiCad cannot check. Treat vendor and spec numbers as hard overrides, treat myths as non-rules, and re-verify after every routing pass.

### Cited Findings
- Vendor limits differ substantially, so device-specific guides must override generic values (DDR: TI 0.75 ps CK skew versus Efinix 75 ps DQ–DQS versus Synaptics ±70 ps). — [TI SPRACN9](https://www.ti.com/lit/pdf/spracn9); [Efinix](https://www.efinixinc.com/docs/pcb-guidelines-ddr-ti-ug-v1.2.pdf); [Synaptics](https://cp.synaptics.com/cognidox/download/NR-159702-AN-APPROVED.pdf)
- TI recommends targeting <20% of the skew limit in layout, leaving margin for package and via effects. — [TI SPRAD66](https://www.ti.com/lit/pdf/sprad66)
- Matching must include via electrical length (Infineon QSPI); route each DDR byte group on one layer with equal via count (TI). — [Infineon AN240090](https://www.infineon.com/assets/row/public/documents/10/42/infineon-an240090-design-and-layout-guide-for-cyrs17b-cyel17b-flash-quad-devices-applicationnotes-en.pdf); [TI SPRACU1](https://www.ti.com/lit/pdf/spracu1)
- Blind adherence to guideline lists is itself a leading cause of bad EMC designs (Hubing), so rules need applicability conditions. — [Hubing annotated list](https://scholarsmine.mst.edu/faculty_work/1672/)
- Prior art for protocol-aware KiCad pair rules exists (kicad-tools). — [kicad-tools #6443](https://github.com/rjwalters/kicad-tools/issues/6443)

### Inferences

**A. Automatic net and interface classification (LLM plus deterministic patterns)**
- Inputs: netlist net names, connected pin names and pin types from symbols, component values and footprints, connector part numbers, and datasheet-derived pin functions.
- Deterministic regex seeds (then LLM confirmation): `USB.*D[PN+-]` or `D[+-]` on a USB connector → USB2; `SS(TX|RX)[PN]`, `USB3_` → USB3; `PCIE.*(TX|RX).*[PN]`, `PER[pn]`, `PET[pn]`, `REFCLK` → PCIe; `HDMI.*D[0-2][PN]`, `TMDS` → HDMI; `CSI.*D\d[PN]`, `DSI.*` → MIPI; `MDI\d?[PN]`, `TRD\d[+-]`, `TX[+-]`/`RX[+-]` on a magnetics part → Ethernet MDI; `DQ\d+`, `DQS\d*_[tc]|[PN]`, `DM\d`, `A\d+`, `BA\d`, `BG\d`, `CK_[tc]`, `CKE`, `ODT`, `CS_n`, `ACT_n`, `RAS/CAS/WE` → DDR; `QSPI_(CLK|SCK|IO[0-3]|CS)` → QSPI; `XTAL|OSC|XI|XO` → crystal. Pair detection uses `_P/_N`, `+/-`, `_t/_c` suffix matching.
- Component roles: connector (footprint library or refdes `J`), TVS/ESD (refdes `D` with an ESD part family), CMC (`L`/`FL` with a common-mode choke part family), magnetics (`T` or an integrated RJ45), AC caps (series C on a SerDes pair), series R (R in series with a single fanout), crystal (`Y`/`X`).
- Output a per-net record: `{interface, role (data/clock/strobe/addr), group (lane, byte), pair_partner, target_Z, skew_tol, group_tol, via_max, spacing_rule, edge_rate_estimate, criticality}`.

**B. Constraint generation (K rules → `.kicad_dru` and net classes)**
- Net classes per impedance class (SE50, DIFF90, DIFF100, DIFF85), with per-layer width and gap from the stackup's field solve.
- Custom rules per interface: `diff_pair_gap`, `diff_pair_uncoupled (max …)`, `skew (max …) (within_diff_pairs)` for P/N; group `skew` rules per DDR byte lane and per QSPI group; `via_count (max …)`; `clearance` between high-speed classes and everything else at 2–3W or 5W (computed per layer); `edge_clearance` for high-speed classes; area-scoped keepouts for the I/O edge zone.
- Store every emitted rule with a `source_url` and a `rule_id` (for example `DP-2`) in a comment, so DRC violations can be explained back to the LLM and the user.

**C. External checks to build (G rules)**, in priority order:
1. **Return-path continuity**: for each high-speed segment, determine the adjacent reference layer(s) from the stackup. Test that the segment, buffered by 1.5 W, lies over filled copper of a GND (or designated) net. Report the length of segment not over plane, plus split crossings (RP-1, RP-2, DP-8).
2. **Reference-change bridging**: at each signal via, find the reference nets above and below on the source and destination layers. If both are GND, require a GND via within R (default 200 mil per TI; prefer ~1 mm). If the nets differ, require a stitching cap within R (RP-3, RP-4).
3. **Via stub length**: from the stackup and the via's used span, compute the stub; flag if it exceeds min(15 mil, 0.3/Gbps in) (TL-3).
4. **Diff-pair geometry**: running skew along the path, serpentine location relative to mismatch features, symmetry of in-line parts, uncoupled segments (DP-3, DP-5).
5. **Crosstalk**: extract parallel-run lengths per aggressor/victim pair per layer. Estimate NEXT from s/W (Bogatin #20) and FEXT from Len/RT on microstrip (Bogatin #21). Flag over budget (XT-1, XT-2).
6. **EMC posture**: connector clustering, high-speed nets inside the I/O-edge buffer, high-speed proximity to the board outline, GND stitching-via max gap ≤ λ/20 at fmax (derived from the knee frequency 0.5/tr), plane-split crossings (EMI-1 to EMI-6).
7. **Protection and filter topology**: TVS distance to connector pin; the trace passes connector → TVS pad → IC with no stub; TVS ground-via distance; CMC distance; Y-cap side; AC cap leg symmetry (EMI-7, EMI-8, DP-5).
8. **Electrical-length classifier**: length × velocity versus tr, to decide which nets need controlled impedance or termination and to flag missing series R at drivers (TL-1, TL-2).

**D. Placer and router behaviour**
- The placement order in §8 becomes a staged placer: hard anchors (connectors, protection), then critical ICs (with fly-by DRAM ordering), then partitions, then passives. The cost function includes high-speed net length, crossings, I/O-zone intrusion and edge proximity.
- The router should route high-speed nets first, on stripline layers when available, minimise layer changes, and drop GND return vias automatically with every signal via that changes reference. Pairs should be routed as coupled with symmetric breakouts. Tuning should be inserted near mismatch sources. Every result should be re-verified with DRC plus the G checks.
- Myth-aware: do not emit 20H, 90° bans (except as P2 style or vendor-mandated), blanket guard traces, ground splits or "minimise all lengths" as constraints. Encode the underlying physics checks instead.

**E. Knowledge-base schema suggestion**
- `rule_id, family, statement, numeric {value, unit, basis: mm|ps|W|h|λ}, physics_why, applies_if {interface, data_rate>, tr<, layer_type}, severity P0–P2, check_type K|G|S, kicad_dru_template, checker_fn, source_url, source_type (spec|vendor|author|blog), confidence`.

### Gaps
- No public source was found describing an existing LLM-driven system that performs return-path or stub checks on KiCad boards. kicad-tools covers pair rules only (based on issue titles).
- Exact KiCad API mechanics for computing zone-fill-aware reference-plane coverage, and the KiCad version-specific `length` and time-domain support, need verification against current docs (fetch was blocked).
