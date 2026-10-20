# High-Speed Digital, Signal Integrity, Differential Pairs and EMI/EMC: A Machine-Actionable Catalog of PCB Placement and Routing Rules (deep pass)

> **Provenance legend (applies to every citation below).**
> - **[P]**: primary source downloaded and read in full this session (author's own article, tech tip, transcript, application note or official documentation).
> - **[P-code]**: read directly from published source code (KiCad GitLab, LearnEMC calculator JavaScript, open-source GitHub repositories).
> - **[S]**: search-result snippet only, from the first pass when fetching was blocked. Not re-read here. A separate verification agent is checking these numbers against primary sources.
>
> **Scope.** Separate agents are (a) verifying the numbers and (b) writing per-interface numeric rule packs (USB/PCIe/DDR/Ethernet/HDMI/MIPI/crystals, board-edge and return-via distances). This pass therefore deepens three things: the physics "why" from primary authors (Ott, Hubing/LearnEMC, Bogatin, Johnson, Hartley, Archambeault); the algorithms (and open-source implementations) for checking each rule KiCad cannot check natively; and stackup selection plus EMC pre-compliance practice.
>
> **Access notes.** Clemson CVEL PDFs (cecas.clemson.edu) failed TLS verification because the server sends an incomplete certificate chain. They were not read; verification was not disabled to work around this. EDN.com and web.archive.org refused connections, so Bogatin's EDN "Rule of Thumb" articles remain [S]. The session's web-search budget was exhausted partway through this pass. Later findings come from direct fetches of known URLs.
>
> **Rule-table schema:** `ID | Rule | Numeric guideline | Why (physics) | Applies when | Sev | Auto-check | Source`. Severity: **P0** = functional failure or spec violation likely; **P1** = margin, EMC or compliance risk; **P2** = good practice. Auto-check: **K** = native KiCad DRC or net-class constraint; **K11** = native only in KiCad master (development, post-10); **G** = custom geometric or physics checker; **S** = simulation.

---

## 1. Return-path fundamentals (current under the signal, plane continuity, split crossing, reference changes, loop area)

### Takeaway
High-frequency return current flows in the plane surface directly beneath (adjacent to) the signal trace. That path minimises loop inductance, and the energy is carried by the fields in the dielectric between trace and plane. About 80% of a microstrip's return current lies within ±3h of the trace centreline, and 99% for stripline. Any break forces a detour, and the detour has three compounding effects (Bogatin's "trifecta"): a reflection at the discontinuity, ground bounce and shared-path crosstalk from the higher-inductance path, and EMI from the voltage developed across the plane, which drives attached cables. Ott ranks layer-change options from best to worst:
1. stay on one layer;
2. change to a layer adjacent to the same plane;
3. change between same-net planes, with a stitching via;
4. change between different-net planes, with a stitching capacitor, which adds 5–10 nH.

### Cited Findings

#### Physics, from primary authors
- **Bogatin.** Signal-return current distributes to minimise loop impedance. Above the frequency where ωL dominates (the "skin depth region"), "the return currents are always flowing directly underneath the signal currents. The path underneath the signal currents is always the lowest loop inductance path." The lowest-impedance distribution puts currents within one conductor far apart (lowering partial self-inductance) and signal and return close together (raising partial mutual inductance). [P] — [Bogatin, "The Case for Split Ground Planes" excerpt, Teledyne LeCroy](https://www.teledynelecroy.com/oscilloscope/blog/signal-return-paths-signal-and-power-integrity-tutorial/)
- **Bogatin.** "A wide, continuous ground plane adjacent to a signal trace will be the lowest cross talk configuration." Crossing a split creates a higher-impedance return path *and* forces the return currents of multiple signals to overlap in the same common path. Result: "reflections from the return path discontinuity, ground bounce from the higher inductance return path, and EMI from the difference in potential between the two regions of the planes." The only benefit a split can offer is reducing *resistive* (low-frequency) coupling, and then only "provided the split or gap in the return plane is ALWAYS parallel to the signal path, and return currents do not cross this gap." [P] — [Teledyne LeCroy / Bogatin](https://www.teledynelecroy.com/oscilloscope/blog/signal-return-paths-signal-and-power-integrity-tutorial/)
- **Bogatin's Rule #7** (best design practices are free habits): "always use a continuous return path adjacent to every signal path." (This corrects the first pass, which numbered it 6.) [P] — [Bogatin's 20 Rules, SIJ](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers)
- **Ott.** "The lowest impedance return path is in a plane directly underneath the signal trace (irrespective of whether this is a power or ground plane)." Because of skin effect, high-frequency currents are surface currents at all frequencies above 30 MHz for 1 oz copper. "A plane in a PCB is really two conductors not one conductor": the top and bottom surfaces can carry different currents. [P] — [Ott, PCB Stack-Up Part 6: Return Path Discontinuities](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html)
- **Ott, layer changes:**
  - A via passing through a plane and continuing on the opposite side of the *same* plane has no return discontinuity, because the clearance hole's wall connects the plane's two surfaces. This is "the preferred way to route a critical signal if two routing layers must be used."
  - Between different planes, interplane capacitance is "not usually large enough to be effective," so the return goes through the nearest decoupling capacitor. Interplane capacitance only becomes effective "considerably above 500 MHz."
  - The capacitor path (via → trace → pad → cap → pad → trace → via) adds "typically 5 to 10 nH."
  - Between same-type planes, use a via "immediately adjacent to the signal via."
  
  [P] — [Ott Part 6](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html)
- **Ott's routing preference order** for clocks and critical traces:
  1. one layer adjacent to a plane;
  2. two layers adjacent to the same plane;
  3. two layers adjacent to two same-type planes, connected with vias where the signal changes planes;
  4. two layers adjacent to different-type planes, connected with capacitors at each change.
  
  [P] — [Ott Part 6](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html)
- **Ott, slots and splits.** "Don't have them!" If a trace must cross one, place small stitching capacitors on either side of the trace (0.001–0.01 µF), "located within 0.1" of the trace." If *both* power and ground planes are split, "the only acceptable solution may be to make sure that no signal traces cross the split plane boundary." [P] — [Ott Part 6](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html)
- **Ott, measured slot effect.** Ground-plane voltage was measured between two points 1" apart under a trace (10 MHz clock, 3 ns rise), with a slot perpendicular to current flow:

  | Slot length | Plane voltage |
  |---|---|
  | none | 15 mV |
  | 1/4" | 20 mV |
  | 1/2" | 26 mV |
  | 1" | 49 mV |
  | 1.5" | 75 mV |
  | row of 15 × 0.052" holes over 1" | 15 mV (no increase) |

  Ott also suggests ordering one set of boards etched but not laminated, to inspect buried planes visually. [P] — [Ott, Slots in Ground Planes](https://hott.shielddigitaldesign.com/techtips/tips-slots.html)
- **Johnson.** "In any high-frequency inductive problem, the relevant magnetic field resides in the space between conductors, not in the conductors themselves." Ground bounce and crosstalk at a pin vary with the magnetic flux between that pin's via and the nearest return-current position, so "the signals closest to a good return suffer the least ground bounce." Spread return connections among signal pins. [P] — [Johnson, "Spread Your Returns"](https://www.sigcon.com/Pubs/edn/SpreadYourReturns.htm)
- **Johnson, the 3-D scaling rule.** Vias behave like tiny connector pins. Shrinking a lossless structure 10× in every dimension makes it work identically, 10× faster. A Euro-connector (0.6" pins) at 5 ns needs about a 10:1 signal-to-ground-pin ratio, so a 0.063" via at 500 ps needs the same 10:1 signal-to-ground-via ratio. This is his reason for "stitching together all of the ground planes … with a carpet of vias." [P] — [Johnson, "Connecting Layers"](https://www.sigcon.com/Pubs/edn/ConnectLayers.htm)
- **Hartley.** "The energy in an electrical circuit is not in the current or voltage; it is in the electric and magnetic fields … they exist in the spaces between [traces and planes]." Signal trace plus return form a waveguide. [P] — [EEJournal, "Matters of Integrity"](https://www.eejournal.com/article/matters-of-integrity/)
- **Hartley.** With 20 ground planes in a board, a signal on L1 with ground on L2 returns 100% in L2. "No current from that trace would be in any other ground layers, because energy is in the dielectric between layers 1 and 2." With two or three signal layers referencing one plane, "all fields intermingling in the dielectric space, all coupling energy into one another and that's one of the places where EMI comes from." [P] — [Altium OnTrack podcast transcript: Hartley on stack-up](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley)
- **Return-current spread (Adamczyk, In Compliance).** Microstrip: about 50% of return current within ±1h of the centreline, about 80% within ±3h, about 97% within ±10h. Symmetric stripline: 99% within ±3h. For stripline between two planes, about 75% flows on the nearer plane directly under the trace. [P] — [Adamczyk, Return-Current Distribution in a Microstrip Line](https://incompliancemag.com/pcb-return-current-distribution-in-a-microstrip-line/); [Adamczyk, Stripline Configurations](https://incompliancemag.com/pcb-return-current-distribution-in-the-stripline-configurations/)
- **Archambeault.** "A tiny fraction of the returning signal current spreads out over the entire plane … called common-mode current." Any layout that "even temporarily diverts the signal current from its associated return path," such as a via changing reference planes, "tends to greatly magnify the amplitude of stray current." [P] — [Archambeault, "Reducing Emissions," EDN 2001 (hosted by Signal Consulting)](https://www.sigcon.com/Pubs/edn/ReducingEmissions.htm)
- **LearnEMC (Hubing).**
  - "Signal currents always return to their source" and "take the path(s) of least impedance." At MHz and above that is the path of least inductance and least loop area. At kHz and below, the least-resistance paths spread out.
  - "Radiation is NOT proportional to loop area. Long traces and cables can carry high-frequency currents without producing significant radiated emissions when they are properly designed."
  - "Don't Split, Gap or Cut the Signal Return Plane … Just don't do it!"
  - Never "route a low-speed trace over a gap in a return plane or put a ferrite on a ground" to filter a signal.
  
  [P] — [LearnEMC, The Most Important EMC Design Guidelines](https://learnemc.com/the-most-important-emc-design-guidelines)
- **LearnEMC.** A trace crossing a gap in its return plane is a *conducted-coupling* source: "The impedance in the path of the return current generates a voltage across the gap. This voltage drives cables referenced to one side of the gap relative to cables referenced to the other side." [P] — [LearnEMC, PCB Layout](https://learnemc.com/pcb-layout)
- **LearnEMC, design review.** A board with solid ground planes "should usually not have ground traces or ground fill on other layers"; ground connections should be "a via connecting directly to the plane." [P] — [LearnEMC, PCB Layout](https://learnemc.com/pcb-layout)
- **Johnson.** Even for differential pairs, "current flows separately on the planes under each trace, almost as if they were two independently routed, single-ended signals." Case study: a 2.5 Gb/s XAUI pair referenced to a power plane, ending at SMA connectors whose grounds tie to a different plane, gave "a horrible-looking eye." Fix: carve a ground region out of the power layer under the connectors. Keep the power/ground gap small (6 mil) and the pair close (about 12 mil) where it crosses the gap. [P] — [Johnson, "Return Current Matters"](https://www.sigcon.com/Pubs/edn/ReturnCurrentMatters.htm)
- **TI SPRAAR7J (Nov 2018, rev. Feb 2023):**
  - Route over a solid GND plane, not across splits or voids.
  - Keep ≥1.5 W from voids.
  - On a GND reference change, place stitching vias "symmetrically within 200 mils (center-to-center, closer is better)" of the signal vias.
  - If a split crossing is unavoidable, use stitching capacitors "1 µF or lower … as close as possible to the plane crossing."
  - Do not overlap planes that do not reference each other, because the overlap capacitance couples RF between them.
  
  [P] — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7)
- **HyperLynx DRC.** Defines "interrupted return path" as three cases: net crossing a gap, net near a plane edge (board edge *or* a large void), and reference plane change. Power-to-ground changes need stitching capacitor(s); ground-to-ground (or same-voltage) changes need stitching via(s). [P] — [Mentor/Siemens whitepaper, "Using HyperLynx DRC to Find EMI Issues" (2014)](https://schematicsforfree.com/files/Manufacturing%20and%20Design/PC%20Board%20Design%20and%20Fabrication/PCB%20Design,%20Layout%20&%20Routing/USING%20HYPERLYNX%20DRC%20TO%20FIND%20EMI%20ISSUES.pdf)
- **Measured.** Increasing ground-plane gap length significantly increased common-mode current. [S] — [Clemson EMCS97-159](https://cecas.clemson.edu/cvel/pdf/EMCS97-159.pdf)
- **GND↔PWR stitching-cap figures (secondary).** About 1–10 nF within about 50 mil; GND via "ideally within 40 mil." [S] — [AtlasPCB](https://www.atlaspcb.com/blog/pcb-via-transition-return-current-path-signal-integrity/); [UGPCB](https://www.ugpcb.com/news/pcb-tech/electronic-design/high-speed-signal-layer-transitions-the-science-of-return-vias-in-pcb-design/)

#### Rule table
| ID | Rule | Numeric | Why | Applies when | Sev | Check | Source |
|---|---|---|---|---|---|---|---|
| RP-1 | Every fast or controlled-impedance trace has continuous plane copper on its reference layer under its full length | 0 mm unreferenced | Return follows the trace; a break forces a detour (reflection, ground bounce, EMI) | Fast-edge nets (§5), all diff pairs, clocks | P0 | K11 (`return_path`, explicit layer) / G (auto layer from stackup) | [Bogatin](https://www.teledynelecroy.com/oscilloscope/blog/signal-return-paths-signal-and-power-integrity-tutorial/) [P]; [Ott P6](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html) [P] |
| RP-2 | Keep traces away from void and plane edges | ≥1.5 W (TI); centreline ≥ w/2 + 3h from plane edge (since about 80% of return lies within ±3h); LearnEMC board-edge rule 2X | Return current spreads about ±3h; truncation crowds it and raises L and fringing | Same | P1 | G | [TI](https://www.ti.com/lit/pdf/spraar7) [P]; [Adamczyk](https://incompliancemag.com/pcb-return-current-distribution-in-a-microstrip-line/) [P]; [LearnEMC](https://learnemc.com/other-good-emc-design-guidelines) [P] |
| RP-3 | Layer-change preference order (Ott 1→4); at a same-net reference change put a GND via next to the signal via | ≤200 mil (5.08 mm) per TI; "immediately adjacent" per Ott | Return must jump planes; via-to-return-via distance × plane spacing is the extra loop | Any layer change that changes reference plane | P0/P1 | G | [Ott P6](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html) [P]; [TI](https://www.ti.com/lit/pdf/spraar7) [P] |
| RP-4 | At a different-net reference change (or an unavoidable split crossing) place stitching capacitor(s), one each side of the trace | 0.001–0.01 µF within 0.1" (2.54 mm) per Ott; ≤1 µF "as close as possible" per TI. Adds 5–10 nH, so avoid where possible | DC-isolated planes need an AC bridge; the capacitor path is inductive | Same | P1 | G | [Ott P6](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html) [P]; [TI](https://www.ti.com/lit/pdf/spraar7) [P] |
| RP-5 | No slots in return planes; flag antipad chains merging into slots | A slot ≥¼" under a trace measurably raises plane voltage (1" ≈ 3.3×); separate holes do not | Slot length sets the detour | All multilayer | P0 | G (merge antipads, then compute slot length) | [Ott slots](https://hott.shielddigitaldesign.com/techtips/tips-slots.html) [P] |
| RP-6 | Avoid power-plane references for high-speed nets; never overlap non-related planes | n/a | Power-plane noise couples in as common mode; overlap couples RF | High-speed | P1 | G | [Johnson](https://www.sigcon.com/Pubs/edn/ReturnCurrentMatters.htm) [P]; [TI](https://www.ti.com/lit/pdf/spraar7) [P] |
| RP-7 | No ground traces or fill on other layers of a board with solid planes; tie ground pins with a direct via | n/a | Shared ground paths, added inductance | Multilayer with planes | P2 | G | [LearnEMC](https://learnemc.com/pcb-layout) [P] |
| RP-8 | Generous GND-GND stitching between planes; signal-to-ground via ratio ≈10:1 for 1.6 mm vias at about 500 ps | ≈10:1 | 3-D scaling of connector-pin crosstalk | Multiple GND planes | P1 | G | [Johnson](https://www.sigcon.com/Pubs/edn/ConnectLayers.htm) [P] |

### Inferences
- The return-current spread (80% within ±3h for microstrip) gives physical grounding for both the "1.5 W from void" and the "edge" rules. Since w ≈ 2h for 50 Ω FR-4 microstrip (Ott: 40–50 Ω at w/h = 2, [P](https://hott.shielddigitaldesign.com/techtips/rulesofthumb.html)), 1.5 W ≈ 3h from the trace edge. TI's rule and the ±3h band are the same physics.
- The checker should treat Ott's case 2 (via through the same plane) as *no discontinuity*. A naive checker that flags every layer change will produce false positives. The open-source return-path checker reviewed in §11 does this correctly: it only flags when the set of reference planes differs before and after the via.
- Ott's slot table and his "holes do not matter" row imply that the checker must merge antipads, clearances and plane voids into connected void polygons and measure void length *perpendicular to the trace*. Simply counting holes is not enough. Dense BGA via fields whose antipads merge are the classic accidental slot.

### Gaps
- Primary Hartley material beyond the 2018 podcast transcript and the EEJournal summary (for example, the slide deck of "The Extreme Importance of PCB Stack-up") was not available. Hartley's recommended fix for the six-layer stack is not stated in the transcript.
- No primary measurement quantified emission increase versus slot length in dB (Ott's table gives plane voltage, not field strength).

---

## 2. Stackup: selection methodology, 2/4/6/8/10-layer assignments, adjacent reference planes, impedance control

### Takeaway
Use Ott's four stackup factors (number of layers, number and type of planes, layer order, spacing) and five objectives:
1. every signal layer adjacent to a plane;
2. signal layers close to their planes;
3. power and ground closely coupled;
4. high-speed signals buried between planes;
5. multiple ground planes.

Eight layers is the fewest that meets all five. On 4- and 6-layer boards, prefer tight signal-to-plane coupling over power-to-ground coupling. Hartley adds two prohibitions: never have two signal layers referencing one plane, and never put power planes adjacent to each other with no ground nearby. He also rejects the ubiquitous 1.6 mm S/P/G/S 4-layer and S/P/S/S/G/S 6-layer stacks because their planes are far apart. Hubing warns that no stack recipe generalises. Impedance (50 Ω SE; 85/90/100 Ω differential) is set per layer by a field solver once h is fixed small.

### Cited Findings
- **Ott, the four factors.** Number of layers; number and types of planes; ordering of layers; spacing between layers. "Usually not much consideration is given except as to the number of layers. In many cases the other three factors are of equal importance." Choose the layer count from five inputs: signals to route and cost; frequency; Class A versus Class B; shielded versus unshielded enclosure; and the team's EMC expertise. [P] — [Ott, PCB Stack-Up Part 1](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-1.html)
- **Ott, rules of thumb:**
  - "A four-layer board will produce 15 dB less radiation than a two-layer board."
  - "Above about ten or fifteen MHz, multi-layer boards should normally be considered."
  - With normal construction, interplane capacitance is inadequate for decoupling below about 500 MHz, so "we should usually opt for tight coupling between the signal and the current return plane."
  - "An eight-layer board is the fewest number of layers that can be used to achieve all five of the above objectives … there is no reason for using more than eight layers other than to accommodate additional signal routing layers."
  - Keep the cross-section symmetric to prevent warp.
  
  [P] — [Ott Part 1](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-1.html)
- **Ott, 4-layer.** The equally spaced S/G/P/S meets only objective 1. Spacing signal layers <0.010" from their planes with a >0.040" core gives smaller loops. At 0.005" trace-to-plane, that is "10 dB or more reduction in the trace loop radiation compared [to] a stack-up with equally spaced layers." It also lowers plane inductance, which reduces common-mode cable radiation, and lowers crosstalk: "For a fixed trace to trace spacing the crosstalk is proportional to the square of the trace height." Alternatives:
  - Fig 3a G/S/S/P: shields the inner signals, but the outer plane gets cut up by pads and rework is hard.
  - **Fig 3b G/(S+P)/(S+P)/G**, power routed as a wide-trace grid and the two grounds stitched around the periphery as a Faraday cage: "the best stack-up possible with a four-layer PCB" (meets objectives 1, 2, 4 and 5).
  - Fig 4 (S+P)/G/G/(S+P): objectives 1, 2 and 5.
  
  [P] — [Ott, PCB Stack-Up Part 2](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-2.html)
- **Ott, 6-layer:**
  - Do not use S/S/G/P/S/S (Fig 5), because layers 1 and 6 are not adjacent to a plane.
  - The common pads-and-low-speed / G / HS / HS / P / low-speed stack (Fig 6) meets objectives 1, 2 and 4, but its planes are separated, so "the decoupling must be designed very carefully."
  - S(H1)/G/S(V1)/S(H2)/P/S(V2) (Fig 7) gives "orthogonal routed signals always reference the same plane." Typical spacing for 0.062" is 0.005/0.005/0.040/0.005/0.005".
  - G/S/G/P/S/G (Fig 8) meets all five objectives but has only two routing layers.
  
  [P] — [Ott, PCB Stack-Up Part 3](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-3.html)
- **Ott, 8-layer:**
  - "An eight-layer board with six routing layers is definitely not recommended … If you need six routing layers you should be using a ten-layer board."
  - Fig 9 (low-speed / P / G / HS / HS / G / P / low-speed) meets all objectives. Add a ground-to-ground via near each signal via when changing between L4 and L5.
  - Fig 10 (G / H1 / G / V1 / H2 / P / V2 / G) uses spacing 0.010/0.005/0.005/0.020/0.005/0.005/0.010".
  - Fig 11 (H1 / G / V1 / G / P / H2 / G / V2) uses 0.006/0.006/0.015/0.006/0.015/0.006/0.006". It has a tight power/ground pair, objectives 1, 2, 3 and 5, and is "one of my favorites."
  
  [P] — [Ott, PCB Stack-Up Part 4](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-4.html)
- **Ott, 10-layer.** Used when six routing layers are needed. Dielectrics are typically ≤0.006" on a 0.062" board, so coupling is automatically tight. Fig 12 (low-speed / G / HS / HS / P / G / HS / HS / G-or-P / low-speed) meets all five objectives. Route clocks on one inner pair and buses on the other, so the central power/ground pair isolates them. Pair orthogonal layers so that each pair references the same plane where possible. [P] — [Ott, PCB Stack-Up Part 5](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-5.html)
- **Ott, summary factors.** Layer spacing; the assignment of signal layer pairs for orthogonal routing; and which signal classes (clock, bus, high-speed, low-frequency) go on which pairs. [P] — [Ott Part 5](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-5.html)
- **Hartley:**
  - Two "worst" 4-layer stacks: (a) a single ground plane on L3 with routing on L1, L2 and L4, so L1 and L2 both reference L3 and their fields "inter-lead … and couple energy" even with orthogonal routing; (b) S/P/G/S on a 1.6 mm board, where the planes are about 1 mm apart, giving high-impedance power delivery and a power↔ground reference change at every L1→L4 via. S/P/G/S is acceptable only if the board is thin (planes "a few mils to maybe at most 10 mils" apart).
  - The common 6-layer S/P/S/S/G/S (planes on 2 and 5) "is even worse than the four layer board," because the planes are farther apart and share dielectric with signals on 3 and 4.
  - Two or three voltage planes adjacent with no ground nearby is "a very serious problem."
  - Hartley disowns stacks he recommended in his older paper "Board Stack-up to Control EMI."
  
  [P] — [Altium OnTrack podcast transcript](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley)
- **LearnEMC (Hubing):**
  - "There is no guideline for the optimum layer stack-up that applies to more than a small subset of all boards … rigidly assigning an entire layer to any particular type of circuit trace is generally not a good idea." [P] — [LearnEMC, Not-So-Good Guidelines](https://learnemc.com/not-so-good-emc-design-guidelines)
  - "Above 25 MHz, all boards should have two ground planes" is "a very old guideline … many perfectly good boards operate at GHz frequencies with only one ground plane." [P] — [same](https://learnemc.com/not-so-good-emc-design-guidelines)
- **LearnEMC, design review:** "If the board has active components with three or more power pins at a given voltage, that voltage should probably be distributed on a closely spaced (i.e., < 0.25 mm) pair of planes. High-frequency decoupling capacitors should be mounted on the side of the board closest to the plane pair." [P] — [LearnEMC, PCB Layout](https://learnemc.com/pcb-layout)
- **LearnEMC.** Route all power planes on the same layer, so different voltage planes do not overlap. The exception is ±12 V-style balanced pairs. A gap between power planes "must be equal to or greater than the spacing between the power planes and the ground planes," otherwise there is little high-frequency isolation. [P] — [LearnEMC, Good EMC Design Guidelines](https://learnemc.com/other-good-emc-design-guidelines)
- **Johnson, crosstalk versus stack.** For broadside-stacked differential pairs in a 20.5 mil cavity, moving each signal layer from 6 mil to 4 mil from its plane (and narrowing traces from 7 to 5 mil for impedance) cut crosstalk from 220 → 143 mV at 13 mil pitch and from 38 → 25 mV at 19 mil pitch. That is about 35% less at every pitch. [P] — [Johnson, "Differential Crosstalk" newsletter](https://www.sigcon.com/Pubs/news/3_20.htm)
- **Johnson.** Among the alternatives he prefers to clock modulation for EMC: solid power and ground planes, *minimising trace-to-plane spacing*, thin packages close to the board, slower clock edges, differential clocks, and low-swing clocks (LVDS, GTL). [P] — [Johnson, "Intentional Clock Modulation"](https://www.sigcon.com/Pubs/edn/clockmod.htm)
- **Ott, impedance rules of thumb (FR-4):**
  - Microstrip Z0 is 60–70 Ω at w/h = 1 and 40–50 Ω at w/h = 2.
  - Stripline Z0 ≈ 0.6 × microstrip; asymmetric stripline ≈ 0.75 ×.
  - Delay is 150 ps/in (microstrip) and 180 ps/in (stripline).
  - Dk is 4.0–5.0, typically 4.5. Z0 ∝ 1/√εr and delay ∝ √εr.
  
  [P] — [Ott, Rules of Thumb](https://hott.shielddigitaldesign.com/techtips/rulesofthumb.html)
- **TI.** Do not overlap planes that do not reference each other (unwanted capacitance passes RF). [P] — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7)
- **Interface impedance targets** (85/90/100 Ω differential, 50 Ω SE): the vendor values from the first pass [S] are being verified by the interface rule-pack agent. — e.g. [TI SLLA414](https://www.ti.com/lit/pdf/slla414); [ADI UG-2212](https://www.analog.com/media/en/technical-documentation/user-guides/public-gmsl2-hardware-design-and-validation-guide.pdf)

#### Candidate stackup library (from Ott [P] with Hartley [P] annotations)
| L | Stack (top→bottom) | Ott objectives met | Notes / conflicts |
|---|---|---|---|
| 4 | S / G / P / S, signal-plane <0.010", core >0.040" | 1, 2 | Hartley: avoid on 1.6 mm if fast edges, because the P/G separation forces P↔G reference changes |
| 4 | G / S+P / S+P / G (power as grid traces) | 1, 2, 4, 5 | Ott's "best 4-layer"; outer grounds cut by pads |
| 4 | S+P / G / G / S+P | 1, 2, 5 | Rework-friendly; no shielding |
| 4 | S / S / G / S | 1 only for L2 | Hartley's "worst": L1 and L2 share one reference |
| 6 | low-speed / G / HS / HS / P / low-speed | 1, 2, 4 | Most common. **Ott**: OK with careful decoupling; **Hartley**: "even worse" than 4-layer, because planes on 2 and 5 are far apart and L3/L4 share a cavity |
| 6 | H1 / G / V1 / H2 / P / V2 (5/5/40/5/5 mil) | 1, 2 | Orthogonal pairs share one plane |
| 6 | G / S / G / P / S / G | all 5 | Only two routing layers |
| 8 | low / P / G / HS / HS / G / P / low | all 5 | GND-GND via at each L4↔L5 change |
| 8 | G / H1 / G / V1 / H2 / P / V2 / G | all 5 | Ott favourite (10/5/5/20/5/5/10 mil) |
| 8 | H1 / G / V1 / G / P / H2 / G / V2 | 1, 2, 3, 5 | Tight P/G core (6/6/15/6/15/6/6 mil); "often preferred" |
| 10 | low / G / HS / HS / P / G / HS / HS / G or P / low | all 5 | Clocks on one HS pair, buses on the other |

### Inferences
- **Stackup selection algorithm (synthesis of Ott, Hartley, LearnEMC and Johnson):**
  1. Estimate the required routing layers (from pin density and BGA escape). If ≥6 routing layers, go to 10 layers (Ott).
  2. From the fastest edge rates, the emission class, and the enclosure, decide whether objective 4 (buried HS layers) is required.
  3. Enumerate candidates from the table above for that layer count.
  4. Reject any candidate where a signal layer is not adjacent to a plane (Ott objective 1; Ott red flag, [P](https://hott.shielddigitaldesign.com/techtips/red_flags.html)); where two signal layers that will carry fast edges reference a single plane from the same side (Hartley); or where power planes are adjacent with no ground (Hartley).
  5. Score the survivors by objectives met, plus a penalty for P↔G reference changes the router will be forced into (Hartley, Ott Part 6), plus plane-pair separation if ≥3 power pins share a rail and power delivery depends on the planes (LearnEMC <0.25 mm).
  6. Choose dielectric thicknesses: minimise signal-to-plane h subject to manufacturable trace width at the target Z0 (Ott: crosstalk ∝ h², and ≥10 dB less loop radiation at 0.005"; Johnson's table). Make up board thickness in the central core. Keep the stack symmetric.
  7. Assign layer *pairs* for orthogonal routing so that each pair references the same plane where possible (Ott Fig 7/10/14).
  8. Field-solve width and gap per (layer, Z target) and emit per-layer net-class or rule widths.
- The Ott-versus-Hartley disagreement on the common 6-layer stack should be encoded as a *warning with rationale* rather than a hard rejection. The deciding variable is plane separation and edge rate. With thin dielectrics, or no fast edges, Ott's caveat (design the decoupling carefully) suffices.
- For a KiCad placer/router, the stackup determines (a) the reference plane of each signal layer (nearest plane by dielectric thickness, as the open-source checker in §11 computes it), (b) the via classes that cause reference changes, and (c) the stub lengths (§5). It should therefore be chosen *before* routing, and arguably before placement density is fixed.

### Gaps
- Hartley's prescribed fix for the S/P/S/S/G/S 6-layer stack is not in the retrieved transcript.
- No primary source was found giving a quantitative scoring function across stackups. The scoring above is synthesis.
- Fabricator-specific stack availability (cores and prepregs) and its effect on achievable h were not researched here.

---

## 3. Differential pairs: coupling, intra-pair skew, inter-pair spacing, symmetry, via pairing, ground vias, serpentine placement

### Takeaway
Differential pairs are *not* self-returning. Each leg's return current flows in the plane under it (Johnson), so every return-path rule in §1 applies to each leg. EMI is dominated by common mode, which comes from driver imbalance and from skew: a skew equal to 20% of the rise time creates a common-mode component of about 10% (Johnson). Tighter spacing therefore buys little EMI once spacing is ≤0.5 mm, and its main layout benefit is less corner-induced skew. Keep geometry symmetric. Budget intra-pair skew relative to the driver's own skew. Correct mismatch near where it arises. Keep serpentine switchbacks short or uncoupled.

### Cited Findings
- **Johnson.** Differential current returns on the plane under each trace separately, "almost as if they were two independently routed, single-ended signals"; referencing a noisy power plane imposes its noise as common mode. [P] — [Johnson, "Return Current Matters"](https://www.sigcon.com/Pubs/edn/ReturnCurrentMatters.htm)
- **Johnson.** For small skew Δt (< rise time), the common-mode peak ≈ Δv·Δt/(2·t_r) relative to a differential peak of Δv. Hence "a 20% skew creates a 10% common-mode component." The common-mode component "creates far more radiation and crosstalk than the differential component." [P] — [Johnson, "CMA of Skew"](https://www.sigcon.com/Pubs/edn/CMAofSkew.htm)
- **Johnson.** With perfect balance, tight spacing cancels radiation (theory: about 40 dB improvement at 1 GHz for 0.5 mm separation, FCC Class B geometry). In practice, driver imbalance limits the benefit: "Unless the outputs balance to better than one part in 100, a common-mode-radiation component of at least 1% … will emanate," so "a differential-trace spacing of 0.5 mm is close enough to deliver all the EMI benefit you are ever likely to get." [P] — [Johnson, "Reducing EMI" (excerpt from *High-Speed Signal Propagation*)](https://www.sigcon.com/Pubs/edn/ReducingEMI.htm)
- **Johnson, corner skew:**
  - The outer trace gains 2p, 1.65p or 1.57p per corner (square, chamfered, rounded; p = pitch). "Chamfering or rounding of differential corners does not eliminate skew."
  - At p = 20 mil and 160 ps/in, that is 5–6.4 ps per corner.
  - Assume driver skew is ≥10% of t_r if unspecified, and size the layout skew budget to it. Examples: 100BASE-TX balanced to 1:1000 gives a budget of about 0.1"; a 2.5 Gb/s driver (200 ps edge) gives about 20 ps.
  - Mitigations: smaller p ("one of the few benefits of tightly coupled pairs"), and place ICs so the pair "leave[s] the driver headed in the same direction in which they enter the receiver." Left and right turns then cancel.
  
  [P] — [Johnson, "Skewed Layout"](https://www.sigcon.com/Pubs/edn/SkewedLayout.htm)
- **Johnson, serpentines.** Avoid long coupled switchbacks. With 8 mil traces, 8 mil spaces and 5 mil height, NEXT ≈ 6%.
  - If a switchback's round-trip delay is ≫ ⅓ t_r, the result is distortion.
  - If it is ≪ ⅓ t_r, arrival is *advanced*: by up to 2× the NEXT coefficient per switchback and up to 4× for a full serpentine.
  - Maximum useful coupled-switchback length is about 1" for a 1 ns edge and about 0.1" for 100 ps. The fix is to stretch the serpentine and remove the coupling.
  - Delay matching must also match configuration (microstrip versus stripline), width, Dk, loading, thresholds and terminations, not just length.
  
  [P] — [Johnson, "Serpentine"](https://www.sigcon.com/Pubs/edn/serpentine.htm)
- **Johnson, differential vias (XFP MSA guidance).** Use an oval clearance around the pair's two vias with ground vias pinning the reference planes at each end. Without the ground vias, via-to-via crosstalk is higher and "falls off less rapidly with distance." No long via stubs (full-length or back-drilled). Crosstalk scales with dI/dt. [P] — [Johnson, "Crosstalk: Differential Vias with Grounds"](https://www.sigcon.com/Pubs/edn/XtkDiffViaGnds.htm)
- **LearnEMC.** "Differential pairs radiate much less than single-ended signals even when the traces in the pair are separated by many times their distance above a ground plane. However, an imbalance in the pair can result in radiation comparable to an equivalent single-ended signal." [P] — [LearnEMC, Good EMC Design Guidelines](https://learnemc.com/other-good-emc-design-guidelines)
- **TI SPRAAR7J.** Pair-to-pair spacing ≥5 W. Keep pairs ≥1.5 W from voids. Stitching vias within 200 mil of signal vias, symmetric. Via stubs <15 mil. [P] — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7)
- **Vendor numbers (first pass):** NXP P/N ≤5 mil with the serpentine at the mismatch point; jog ≥3 W / ≥15 mil; USB3/PCIe/SATA ≤5 mil; USB 2.0 ≤50 mil. [S] — [NXP AN10798](https://www.nxp.com/docs/en/application-note/AN10798.pdf); [NXP AN10373](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/powerquicc/2284/2/philips_PCIe_pcb_routing_guide.pdf). These are being verified by the rule-pack agent.
- **KiCad 9 `skew`** measures "the difference between the length of each net and the longest net that is matched by the rule." `within_diff_pairs` tests each pair separately. `diff_pair_gap` is not tested on non-parallel portions such as fanout. `diff_pair_uncoupled` counts length that is non-parallel or outside the gap range. (This corrects the first pass, which said "average.") [P] — [KiCad 9.0 PCB Editor docs](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html)
- **kicad-happy (MIT)** implements V_CM = V_diff × skew / (2 T_rise), consistent with Johnson's formula, and per-protocol skew limits (USB HS 25 ps, PCIe 5 ps, Ethernet 50 ps, HDMI 20 ps; values unverified). [P-code] — [kicad-happy emc-precompliance.md](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md)

#### Rule table
| ID | Rule | Numeric | Why | Applies when | Sev | Check | Source |
|---|---|---|---|---|---|---|---|
| DP-1 | Constant width and gap at target Zdiff; both legs over continuous plane | Interface Zdiff | Each leg returns under itself; gaps cause mode conversion | All pairs | P0 | K (width/gap) + K11/G (return path per leg) | [Johnson](https://www.sigcon.com/Pubs/edn/ReturnCurrentMatters.htm) [P] |
| DP-2 | Intra-pair skew ≤ min(interface spec, budget derived from driver balance) | CM% ≈ ½ × skew/t_r; 20% skew → 10% CM | Skew converts differential to common mode | All pairs | P0 | K (`skew … within_diff_pairs`, length or time domain in KiCad 10) | [Johnson](https://www.sigcon.com/Pubs/edn/CMAofSkew.htm) [P] |
| DP-3 | Place ICs so the pair exits and enters in the same direction; otherwise compensate near each bend | Corner adds 1.57–2 p | Turn skew accumulates and does not cancel | Long pairs, many turns | P1 | G (running skew) | [Johnson](https://www.sigcon.com/Pubs/edn/SkewedLayout.htm) [P] |
| DP-4 | Serpentine: round-trip delay of each coupled switchback ≪ ⅓ t_r, or separate switchbacks enough that coupling is negligible | ≈1" per ns of t_r maximum when coupled | Coupled switchbacks advance timing or distort | Tuned nets | P1 | G (switchback length versus t_r; gap versus h) | [Johnson](https://www.sigcon.com/Pubs/edn/serpentine.htm) [P] |
| DP-5 | Spacing tighter than about 0.5 mm buys no EMI; choose the gap for Zdiff and density | ≤0.5 mm is enough | Driver imbalance (≥1%) dominates radiation | All | P2 | n/a | [Johnson](https://www.sigcon.com/Pubs/edn/ReducingEMI.htm) [P] |
| DP-6 | Ground vias pinning the planes beside each differential via pair; no stubs | Pattern per XFP / TI 200 mil | Contains via fields; lowers via-to-via crosstalk | Multi-Gb/s | P1 | G | [Johnson](https://www.sigcon.com/Pubs/edn/XtkDiffViaGnds.htm) [P]; [TI](https://www.ti.com/lit/pdf/spraar7) [P] |
| DP-7 | Pair-to-pair ≥5 W | 5 W | Lane crosstalk | Multi-lane | P1 | K (clearance with `A.inDiffPair('*') && !AB.isCoupledDiffPair()`) | [TI](https://www.ti.com/lit/pdf/spraar7) [P]; [KiCad 9 docs](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html) [P] |
| DP-8 | Limit uncoupled length | Interface-specific | Zdiff change, common mode | All | P1 | K (`diff_pair_uncoupled (max …)`) | [KiCad 9 docs](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html) [P] |

### Inferences
- **Skew budget derivation for the constraint generator:** skew_max = min(spec value, k × t_r), with k ≈ 0.1 to match a typical digital driver's own skew (Johnson), or tighter for balanced analog-style links such as Ethernet magnetics. Converting ps to mm uses the per-layer unit delay. KiCad 10 tuning profiles hold exactly this, and Ott gives about 150/180 ps/in for microstrip/stripline.
- "Serpentine near the mismatch" should be implemented as a running-skew walk along both legs, inserting compensation where |running skew| exceeds a threshold (for example 0.2 × budget). End-of-route totals alone are not enough. This follows from Johnson's corner-skew accounting and his point that turn skew converts mode locally.

### Gaps
- No primary source gave a numeric "return GND via count or distance per differential via" for general boards beyond TI's 200 mil and the XFP pattern figure (the figure dimensions were not legible in the text extraction).

---

## 4. Interface-specific rules (USB, PCIe, Ethernet, HDMI, MIPI, DDR, SPI/QSPI, clocks/crystals, SerDes AC caps)

### Takeaway
Interface rules reduce to impedance class, skew budgets, via count, and the placement order of in-line parts (AC caps, ESD, CMC, magnetics). Device-vendor layout guides override generic values. *A separate agent is producing verified per-interface rule packs.* This section keeps the first-pass defaults (mostly [S]) and adds only the primary-read items from this pass.

### Cited Findings
- **TI SPRAAR7J (primary, rev. Feb 2023):** 1.5 W from voids; 5 W pair spacing; 200 mil stitching vias; via stubs <15 mil, back-drill longer; stitching caps ≤1 µF at unavoidable split crossings; no overlap of non-referencing planes. [P] — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7)
- **Telian, connector pads as stubs.** Signals "must route into connector pads at the end opposite the connector solder leg exit"; routing from the back side leaves about a 50 mil pad stub, "too long for even an 8 Gbps stub." 25+ Gb/s standards require surface-mount connectors because press-fit pins are stubs. [P] — [Telian, "Fixing the Problem of Stubs," SIJ](https://www.signalintegrityjournal.com/articles/2962-fixing-the-problem-of-stubs)
- **Johnson.** Never use an intentionally modulated (spread-spectrum) clock as the reference for data-communication transceivers (Ethernet, Fibre Channel, SONET and others), PLL-based CPUs, or RF subsystems. [P] — [Johnson, "Intentional Clock Modulation"](https://www.sigcon.com/Pubs/edn/clockmod.htm)
- **LearnEMC.** Place clock drivers adjacent to oscillators, and more generally "any component … that communicates exclusively with another component … should be located close to that component." [P] — [LearnEMC, Good EMC Design Guidelines](https://learnemc.com/other-good-emc-design-guidelines)
- **emcvisual (0BSD-style licence) crystal rule:** crystal closer than 5 mm to the board edge or 10 mm to a cable connector is flagged; foreign lines under the crystal package without an intervening plane are flagged. It cites Infineon AP24026 and ST AN2867. [P-code] — [emcvisual RULES.md](https://github.com/tombueng/emcvisual/blob/main/docs/RULES.md)
- **Ethernet.** Johnson: a 100BASE-TX transceiver with a well-balanced transformer and CMC may be balanced to 1:1000, so the layout and connector skew budget is about 0.1". [P] — [Johnson, "Skewed Layout"](https://www.sigcon.com/Pubs/edn/SkewedLayout.htm)
- **First-pass defaults [S]** (being verified elsewhere):
  - USB 2.0: 90 Ω ±15%, P/N ≤50 mil.
  - USB3/PCIe: ≤5 mil intra-pair; USB3 ≤2 vias; AC caps 0402, symmetric.
  - DDR4: fly-by; byte-lane-only matching (TI).
  - LPDDR4: CK skew ≤0.75 ps (TI).
  - QSPI at 133 MHz: IO ±30 mil, SCK–IO ±200 mil (Infineon).
  - Ethernet: PHY↔magnetics ≥25 mm (Pulse); Bob Smith termination 75 Ω + about 1000 pF to chassis.
  - HDMI/MIPI: 100 Ω, ±5 mil.
  - Crystal: AN2867 guard ring and local ground.
  
  — [TI SLLA414](https://www.ti.com/lit/pdf/slla414); [Microchip AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf); [TI SPRACU1](https://www.ti.com/lit/pdf/spracu1); [TI SPRACN9](https://www.ti.com/lit/pdf/spracn9); [Infineon AN240090](https://www.infineon.com/assets/row/public/documents/10/42/infineon-an240090-design-and-layout-guide-for-cyrs17b-cyel17b-flash-quad-devices-applicationnotes-en.pdf); [Pulse](https://www.mouser.com/pdfDocs/pulse_layout_considerations_final.pdf); [ADI UG-2212](https://www.analog.com/media/en/technical-documentation/user-guides/public-gmsl2-hardware-design-and-validation-guide.pdf); [ST AN2867](https://www.st.com/resource/en/application_note/an2867-guidelines-for-oscillator-design-on-stm8afals-and-stm32-mcusmpus-stmicroelectronics.pdf)

### Inferences
- Interface rows should carry a `t_r` (or UI) field, so that the generic physics checks in §1, §3, §5 and §6 can be parameterised automatically. Examples: the critical-length classifier, serpentine switchback limits, stub limits from 0.3/Gb/s, and skew budgets as a fraction of t_r.

### Gaps
- Numeric verification of all interface values is delegated to the rule-pack agent.

---

## 5. Termination, stubs, via stubs and backdrilling, electrical length

### Takeaway
A net needs transmission-line treatment when its delay is a significant fraction of the *rise time*, not the clock period. Johnson's practical band is a one-way delay of 1/10 to 1/3 of t_r, and he simulates anything over 1/6. LearnEMC urges slowing the edge first and treating matched termination as a last resort, because matched terminations sharpen edges and draw more current. Termination value also sets current amplitude and therefore EMI (Archambeault: 10–20 dB at clock harmonics). Stubs resonate at the quarter wave, and the industry rule is stub [in] < 0.3 / data rate [Gb/s]. Stub length includes pad rings, not just the barrel. KiCad 10 can model backdrills, and KiCad master adds a native `stub_length` DRC for net-chain branches.

### Cited Findings
- **Johnson.** "The critical line length beyond which many people use terminators varies from about 1/10 to 1/3 the length of the rising edge," depending on driver impedance, load impedance, and how perfect the first edge must be. A low-impedance driver into a large capacitive load can need termination at ≤1/10. "As a rule of thumb, I generally simulate all lines longer than about 1/6 of the risetime." [P] — [Johnson, "Line Length"](https://www.sigcon.com/Pubs/news/3_14.htm)
- **LearnEMC.** "A trace with a propagation delay of more than half the transition time … must have a matched termination." But: "Don't use a matched termination unless the risetime has already been slowed as much as possible, and the trace length has been shortened as much as possible. Matched terminations are undesirable because they draw more power and make it more difficult to control risetimes." [P] — [LearnEMC, Good EMC Design Guidelines](https://learnemc.com/other-good-emc-design-guidelines)
- **LearnEMC** rejects "terminate all traces longer than λ/4 at the highest frequency of interest": relate delay to rise time instead, "the best solution is to slow the risetime." [P] — [LearnEMC, Some of the Worst EMC Design Guidelines](https://learnemc.com/some-of-the-worst-emc-design-guidelines)
- **LearnEMC** rejects "nets driven faster than 1 V/ns must have a series resistor" and "capacitively-loaded nets must have source impedance ≥ Z0/4" as decision criteria. [P] — [LearnEMC, Not-So-Good Guidelines](https://learnemc.com/not-so-good-emc-design-guidelines)
- **LearnEMC.** "By default, it is a good idea to assume every digital signal trace driving a capacitive load needs a series resistor to control its transition time. Then, remove the resistor from any trace where it is clearly not required." For matched-terminated controlled-impedance lines, use slew-controlled logic instead. A transition time of about 20% of the bit period is a reasonable compromise. For capacitive loads, use resistors, not ferrites. [P] — [LearnEMC, PCB Layout](https://learnemc.com/pcb-layout); [LearnEMC, Most Important Guidelines](https://learnemc.com/the-most-important-emc-design-guidelines)
- **Archambeault.** Termination values that all give acceptable *voltage* waveforms can give "vastly different currents." On a 12", 133 MHz clock, raising the source termination from 10 Ω toward 39 Ω reduced current amplitude at high clock harmonics by 10–20 dB, "with a concomitant reduction in EMI." "If you care about EMI, select the termination value that minimizes the intensity of current." [P] — [Archambeault, "Reducing Emissions"](https://www.sigcon.com/Pubs/edn/ReducingEmissions.htm)
- **Ott rule of thumb.** Maximum unterminated stub length L[in] = t_r[ns]. [P] — [Ott, Rules of Thumb](https://hott.shielddigitaldesign.com/techtips/rulesofthumb.html)
- **Telian, explaining Bogatin's rule.** "Eric Bogatin introduced the helpful rule of thumb that predicts the ¼-wavelength PCB stub lengths in inches to be 3/Gbps … Eric encouraged everyone to play it 10x safe, and keep stubs smaller than 0.3/Gbps."
  - Demonstration: a 12" 12 Gb/s channel with a 0.250" stub transmits <2% at 6 GHz (eye closed); with 0.025" there is no visible change.
  - At 30 Gb/s the allowed stub is about 10 mil, so pads become stubs. Example: a non-back-drilled via's "stub" is 11 mil = 4 mil pad ring + 3 mil dielectric + 4 mil bottom pad ring. "Add in the length of the middle pad ring even on a back-drilled via."
  - Alternatives to backdrilling: keep signals on near-outer layers (break out on L1 and via to L15 of 16); sequential lamination; blind or buried vias. Decide the stub strategy before the stackup and signal layers are defined.
  
  (Correction: the first pass attributed this article to Bogatin. It is by Donald Telian, quoting Bogatin's rule.) [P] — [Telian, SIJ](https://www.signalintegrityjournal.com/articles/2962-fixing-the-problem-of-stubs)
- **Quarter-wave resonance in FR-4:** f[GHz] ≈ 1.5/Len[in] ≈ 3.8/Len[cm] (Bogatin Rule of Thumb #17). [S] — [EDN #17](https://www.edn.com/the-quarter-wave-stub-frequency-rule-of-thumb-17/)
- **TI.** "TI recommends keeping via stubs to less than 15 mils. Longer stubs must be back-drilled." Back-drilling uses a drill slightly larger than the original hole. [P] — [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7)
- **KiCad 10** supports backdrills on vias (Via Properties) and pads (Pad Properties → Backdrill tab): controlled-depth re-drilling "from one or both sides" to remove unused barrel, drawn with a "must-cut" layer. [P] — [KiCad 10.0 PCB Editor docs](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html)
- **KiCad master (post-10, unreleased).** New constraint `stub_length` (time-domain capable) checks stubs of a *net chain*. The topology builder computes trunk length and delay and each stub's branch point, length and delay. Error: "Stub length (%s) out of range for net chain '%s'." [P-code] — [drc_rule_parser.cpp](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/drc/drc_rule_parser.cpp); [drc_test_provider_matched_length.cpp](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/drc/drc_test_provider_matched_length.cpp)
- **HyperLynx DRC** includes a "Via stub length" rule, and treats a long via stub as both an SI discontinuity and a potential radiator. [P] — [HyperLynx DRC EMI whitepaper](https://schematicsforfree.com/files/Manufacturing%20and%20Design/PC%20Board%20Design%20and%20Fabrication/PCB%20Design,%20Layout%20&%20Routing/USING%20HYPERLYNX%20DRC%20TO%20FIND%20EMI%20ISSUES.pdf)

#### Rule table
| ID | Rule | Numeric | Why | Applies when | Sev | Check | Source |
|---|---|---|---|---|---|---|---|
| TL-1 | Classify as electrically long if one-way delay > tr/6 (simulate); termination likely needed above about tr/3, or tr/2 per LearnEMC | 1/10–1/3 band; 1/6 trigger | Reflections when round trip is comparable to t_r; worse with low-Z drivers and capacitive loads | Nets with known t_r | P1 | G | [Johnson](https://www.sigcon.com/Pubs/news/3_14.htm) [P]; [LearnEMC](https://learnemc.com/other-good-emc-design-guidelines) [P] |
| TL-2 | Prefer slowing edges (slew control, series R) over matched termination; default series R on capacitively loaded digital nets, remove when clearly unnecessary | Transition time ≈20% of bit period | Spectral energy above 1/(πt_r) drops; matched terms sharpen edges and draw current | Digital nets | P1 | G (series R near driver?) | [LearnEMC](https://learnemc.com/pcb-layout) [P] |
| TL-3 | Choose the source-termination value for minimum current, not just acceptable voltage | 10–20 dB harmonic current difference in Archambeault's example | Emissions follow current | Clocks and strobes | P1 | S (current waveform) | [Archambeault](https://www.sigcon.com/Pubs/edn/ReducingEmissions.htm) [P] |
| TL-4 | Via stub (barrel + pad rings beyond the last used layer) | < min(15 mil, 0.3/Gb/s in) | Quarter-wave notch | SerDes ≳3 Gb/s | P0 | G (stackup); KiCad 10 backdrill fields as the remedy | [TI](https://www.ti.com/lit/pdf/spraar7) [P]; [Telian](https://www.signalintegrityjournal.com/articles/2962-fixing-the-problem-of-stubs) [P] |
| TL-5 | Trace stubs (T-branches, test points) | L[in] ≤ t_r[ns] (Ott) or tighter | Stub reflections and resonance | All fast nets | P1 | K11 (`stub_length` on net chains) / G | [Ott](https://hott.shielddigitaldesign.com/techtips/rulesofthumb.html) [P]; [KiCad master](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/drc/drc_test_provider_matched_length.cpp) [P-code] |
| TL-6 | Route into connector and SMT pads from the end that leaves no pad stub | Pad overhang ≈0 | A ~50 mil pad is a stub at ≥8 Gb/s | ≥8 Gb/s | P1 | G (track entry point versus pad's lead-exit side) | [Telian](https://www.signalintegrityjournal.com/articles/2962-fixing-the-problem-of-stubs) [P] |

### Inferences
- **Via-stub algorithm (KiCad):**
  1. Parse the stackup to get z(top) and z(bottom) of every copper layer, including copper thickness. KiCad's SWIG bindings do not expose the stackup, so either parse the `.kicad_pcb` (as the return-path checker in §11 does) or use the IPC API `Board.get_stackup()`.
  2. For each via of a classified net, take the drilled span (through, blind or buried) minus any backdrill (KiCad 10 via backdrill settings).
  3. Find the layers where the net actually connects to the via: track endpoints within the via pad radius, plus SMD pads hit by the via.
  4. stub_top = z(first connected layer) − z(start of plated barrel); stub_bottom = z(end of plated barrel) − z(last connected layer). Add pad-ring copper thickness and any non-removed unused pads (Telian).
  5. Report f_res ≈ c / (4 · stub · √εr). Flag if stub > 0.3/Gbps [in] or > 15 mil, or if f_res < 3 × (data rate / 2).
  
  The via unit delay in a KiCad 10 tuning profile can share the same stackup model.
- The critical-length classifier needs t_r per driver. Where IBIS is absent, an LLM can estimate t_r from the part family, but must mark it as an assumption. Johnson's "1/6 of t_r → simulate" makes a sensible trigger for flagging nets for SI review rather than for automatically adding terminations.

### Gaps
- No primary source quantified how much unused-pad removal on inner layers shortens the effective stub; Telian only says to count pad rings.
- Parallel-termination placement rules were not researched.

---

## 6. Crosstalk: spacing, parallel-run limits, orthogonal adjacent layers, guard traces

### Takeaway
Over a solid plane, worst-case near-end coupling between parallel traces is K ≈ 1/(1+(D/H)²) (Johnson; D = centre-to-centre separation, H = height to the nearest plane). Height and separation are "your best friends": crosstalk scales roughly with H²/D². Ott's numbers: <2% at s = 4h for microstrip and s = 2h for stripline. Bogatin: 2W spacing at 50 Ω gives about 2.5% NEXT. These agree within the precision of a rule of thumb. On boards with solid planes, guard traces and ground fill do almost nothing (Johnson, LearnEMC). Spacing and lower H are the levers. Microstrip far-end crosstalk grows with coupled length and inversely with rise time. Aggressor contributions add.

### Cited Findings
- **Johnson.** "For parallel lines, the worst case value of the coefficient of coupling K … is approximately K = 1/(1+(D/H)²) where D is the separation between the centerlines of the traces, and H is the effective height above the nearest reference plane."
  - This is the NEXT coefficient for fast edges; FEXT is less.
  - "If two-times the propagation delay of the parallel traces is less than the risetime of the signal, then the crosstalk reduces further, proportional to the ratio of those two quantities."
  - Example: H = 0.005", D = 0.5", so D/H = 100 and coupling is 1:10,000 (80 dB), "independent of signal rise time." Total crosstalk on a victim is the sum over aggressors.
  - For extra isolation, encapsulate between two same-voltage planes with a row of vias on about ¼" centres (and measure with and without).
  
  [P] — [Johnson, "Noise Isolation" newsletter](https://www.sigcon.com/Pubs/news/2_13.htm)
- **Johnson.** For a bus, "add crosstalk from your two nearest neighbors, plus a little from the next two traces over." Closely spaced differential pairs do not cancel aggressor coupling much, because "crosstalk from +A+ to +B+ is MUCH stronger than crosstalk from -A- to -B-." [P] — [Johnson, "Differential Crosstalk"](https://www.sigcon.com/Pubs/news/3_20.htm)
- **Johnson, guard traces.** "On a digital pcb that already has solid reference planes, guard traces provide little benefit … That plane is the biggest, fattest, best-looking guard trace you will ever see … Unless you can lay out a guard trace closer to the signal trace than the solid reference plane, and make it wider and better than the plane, the guard trace provides almost no benefit … crosstalk between parallel traces changes approximately in proportion to the square of trace height and inversely with the square of separation." A guard must be grounded at both ends to be effective. Guards help on two-layer analog boards (order-of-magnitude at audio). [P] — [Johnson, "Guard Traces"](https://www.sigcon.com/Pubs/news/15_02.htm)
- **Johnson, ground fill.** Useful on two-layer boards without planes (it reduces capacitive coupling). "On a multilayer board with solid power and ground planes, the ground fill serves no function," and it "modulat[es] the impedance of any traces that run adjacent." High-speed digital circuits are low-impedance, so coupling is mainly magnetic, which needs continuous parallel return conductors (planes), not isolated fill. [P] — [Johnson, "Ground Fill"](https://www.sigcon.com/Pubs/edn/GroundFill.htm)
- **Ott.** "For < 2% Crosstalk: s = 4h for Microstrip, and s = 2h for Stripline." For fixed spacing, crosstalk ∝ (trace height)². [P] — [Ott, Rules of Thumb](https://hott.shielddigitaldesign.com/techtips/rulesofthumb.html); [Ott Part 2](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-2.html)
- **LearnEMC.** Guard traces "are not useful often enough to warrant a mention … We recommend that you not use guard traces unless there is a specific known problem you are trying to address." [P] — [LearnEMC, Not-So-Good Guidelines](https://learnemc.com/not-so-good-emc-design-guidelines)
- **LearnEMC.** Crosstalk *into I/O traces* is a key EMC path: "If the board layout software can't check for I/O traces that are routed in the vicinity of high-speed traces, then this should be done manually." [P] — [LearnEMC, PCB Layout](https://learnemc.com/pcb-layout)
- **Ott.** Analog and digital signals should not cross; if they must, cross at right angles. [S] — [Ott EE Times](https://www.eetimes.com/partitioning-and-layout-of-a-mixed-signal-pcb-3/)
- **Bogatin #20 / #21.** 50 Ω FR-4: s ≈ 2w gives NEXT ≈ 2.5%. Microstrip FEXT ≈ 0.5% × Len[in]/RT[ns] at tight spacing. [S] — [EDN #20](https://www.edn.com/how-far-is-far-enough-signal-line-spacing-for-acceptable-near-end-crosstalk-rule-of-thumb-20/); [EDN #21](https://www.edn.com/how-to-engineer-acceptable-far-end-crosstalk-rule-of-thumb-21/)
- **Simonovich, DesignCon 2013.** Guard traces worth considering only for more than −60 dB isolation at high density. [S] — [DesignCon 2013 paper](https://www.signalintegrityjournal.com/ext/resources/article-images-2019/Guard-Traces---Love-Them-or-Leave-Them/4567Guard_Trace_DesignCon-2013-rev14_Final.pdf?trk=public_post_comment-text)
- **HyperLynx DRC.** "I/O coupling" rule: high-speed nets coupling into I/O nets. [P] — [HyperLynx whitepaper](https://schematicsforfree.com/files/Manufacturing%20and%20Design/PC%20Board%20Design%20and%20Fabrication/PCB%20Design,%20Layout%20&%20Routing/USING%20HYPERLYNX%20DRC%20TO%20FIND%20EMI%20ISSUES.pdf)

#### Rule table
| ID | Rule | Numeric | Why | Applies when | Sev | Check | Source |
|---|---|---|---|---|---|---|---|
| XT-1 | Spacing from a K budget: D ≥ H·√(1/K − 1) | K = 2–5% → D ≈ 4.4–7H centre-to-centre; Ott s = 4h (microstrip), 2h (stripline) for <2% | Mutual L and C fall as 1/(1+(D/H)²) | Fast-edge SE nets | P1 | K (class-to-class clearance, per layer in mm) | [Johnson](https://www.sigcon.com/Pubs/news/2_13.htm) [P]; [Ott](https://hott.shielddigitaldesign.com/techtips/rulesofthumb.html) [P] |
| XT-2 | Reduce coupling via H first (stackup) | crosstalk ∝ H² | Field confinement | Stackup design | P1 | n/a | [Ott](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-2.html) [P]; [Johnson](https://www.sigcon.com/Pubs/news/3_20.htm) [P] |
| XT-3 | Saturation: NEXT scales by min(1, 2·T_coupled/t_r) | n/a | Short coupled runs do not reach saturated NEXT | All | P2 | G | [Johnson](https://www.sigcon.com/Pubs/news/2_13.htm) [P] |
| XT-4 | Sum aggressors (two nearest neighbours plus the next two) | Total victim budget (e.g. 5%) | Superposition | Buses | P1 | G | [Johnson](https://www.sigcon.com/Pubs/news/3_20.htm) [P] |
| XT-5 | No guard traces or ground fill on multilayer boards with solid planes unless a specific problem is shown; on 2-layer boards, guards must be grounded at both ends | n/a | The plane is the best guard; fill modulates Z0 | Multilayer | P2 | G (flag floating or one-end-grounded copper) | [Johnson](https://www.sigcon.com/Pubs/news/15_02.htm) [P]; [LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines) [P] |
| XT-6 | Keep fast nets away from I/O nets (I/O coupling) | Use the K budget with a stricter target (I/O nets drive cables) | Noise on I/O nets leaves the board as common mode | All boards with cables | P1 | G | [LearnEMC](https://learnemc.com/pcb-layout) [P] |
| XT-7 | Avoid broadside parallel runs on adjacent signal layers; cross at 90° | n/a | Broadside coupling is strong | Dual stripline | P2 | G | [Ott EE Times](https://www.eetimes.com/partitioning-and-layout-of-a-mixed-signal-pcb-3/) [S]; [Hartley](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley) [P] |

### Inferences
- **Cross-validation:** for 50 Ω microstrip, w ≈ 2h (Ott). Bogatin's s = 2w therefore gives D = s + w = 6h, and Johnson's formula gives K = 1/(1+36) ≈ 2.7%, matching Bogatin's 2.5%. Ott's s = 4h gives the same D = 6h, so <3% (Ott quotes <2%). The three authorities agree. Johnson's closed form is the natural one to encode, because it needs only D and H from the board.
- **Crosstalk extraction algorithm** (see §11 for implementation references):
  1. Spatially hash all track segments of classified nets per layer.
  2. For each same-layer segment pair on different nets within angle tolerance (about 5°), compute overlap length and edge spacing s, so D = s + (w1 + w2)/2.
  3. Also check broadside pairs on adjacent signal layers by projected overlap and vertical separation.
  4. Compute K = 1/(1+(D/H)²) × min(1, 2·T_overlap/t_r_aggressor).
  5. For microstrip, add a FEXT estimate ∝ length/t_r (Bogatin #21 [S]).
  6. Accumulate per victim; flag victims above budget, with stricter budgets for I/O and analog victims.

### Gaps
- Bogatin's EDN rule-of-thumb articles could not be read (EDN refused connections). The FEXT coefficient remains [S].

---

## 7. EMI/EMC: mechanisms, connectors and edges, stitching, filtering, chassis, ESD, CMCs, slots, grounding, plus pre-compliance practice

### Takeaway
Below about 100 MHz, a board is electrically small, so the efficient antennas are cables and chassis. "As little as 1 mV driving one antenna part relative to another could cause a radiated emissions failure" (Hubing), and stricter standards push the threshold toward 100 µV. Board EMC is therefore about *never developing a voltage between two cable reference points*. The steps:
- keep all connectors on one edge or corner, and never put high-speed circuitry between connectors;
- keep the return plane unbroken;
- keep I/O traces short, filtered or series-terminated at the connector, and away from fast nets;
- control transition times.

Pre-compliance practice: hold an EMC design review before the first layout and again after the first draft; visualise each test's current path; include footprints for optional filters, transient protection and shields; measure cable common-mode current with a clamp. Ott's limit is <5 µA (Class B, ≥1 m cable), Hartley's is 8–10 µA.

### Cited Findings

#### Mechanisms and quantitative thresholds
- **LearnEMC, three conditions for an unintentional antenna:**
  1. two parts;
  2. both not electrically small;
  3. a voltage induced between them.
  
  Below about 100 MHz, the viable antenna parts are attached cables and metal chassis. Good antenna parts above 100 MHz: tall components, heatsinks, enclosure seams, sparsely populated power planes. Poor antenna parts: ICs, microstrip and stripline traces, and densely populated power planes. [P] — [LearnEMC, PCB Layout](https://learnemc.com/pcb-layout)
- **LearnEMC.** "It's important to hold all the antenna parts to the same potential. As little as 1 mV driving one antenna part relative to another could cause a radiated emissions failure." In review: "ensure that no two antenna parts can be driven by a millivolt or more at any radiated emissions test frequency. For emissions requirements more stringent than CISPR 32 Class B, this voltage might need to be as low as 100 microvolts." [P] — [LearnEMC, PCB Layout](https://learnemc.com/pcb-layout)
- **LearnEMC, magnetic coupling between connectors.** A trace between two connectors returns current in the plane, and "the flux wrapping the plane effectively produces a voltage that can drive things referenced to the plane on opposite sides … tens of milliamps at tens of megahertz will effectively induce millivolts." The voltage increases with trace width and height. "Stripline traces with currents returning above and below the trace produce no voltage at all." Fix: all external connections on one edge, with no fast traces near and parallel to that edge; or a metal chassis bonded to the plane at both connectors. [P] — [LearnEMC, PCB Layout](https://learnemc.com/pcb-layout)
- **LearnEMC Guideline #3.** "Don't Locate High-Speed Circuitry Between Connectors … one of the most common problems we've encountered … high-speed circuitry located between connectors can easily develop potential differences of a few millivolts or greater between the connectors." [P] — [LearnEMC, Most Important Guidelines](https://learnemc.com/the-most-important-emc-design-guidelines)
- **LearnEMC Guideline #4.** "A board operating with a clock speed of 100 MHz should never fail to meet a radiated emissions requirement at 2 GHz." Transition time ≈20% of the bit period. Methods, in order: slew-controlled logic; a series resistor for capacitive loads (not ferrites); a parallel capacitor for matched loads (not recommended). [P] — [LearnEMC, Most Important Guidelines](https://learnemc.com/the-most-important-emc-design-guidelines)
- **Hubing / Su / Zhu: Maximum Radiated Emissions Calculator, common-mode algorithm.** Read from the calculator's JavaScript. [P-code] — [LearnEMC CM EMI Calculator](https://learnemc.com/ext/calculators/mremc/cmode.php); [CMode_algr.js](https://learnemc.com/ext/calculators/mremc/calculator/CMode_algr.js)
  - Return-plane partial inductance: L_return = (µ0/π)·t·l_t / w_e / √(1 − 4(1 − 2t/w_e)·offset²/w_e²). Here t = trace height, l_t = trace length, w_e = d1 + d2 (distances from the trace to the two board edges), and offset = |d1 − d2|/2.
  - Trace inductance: L_trace = √(µ0ε0)·l_t·Z0.
  - Imbalance factor: h = L_return/(L_return + L_trace).
  - Voltage-driven: V_cm = h·V_dm. Current-driven: V_cm = 2πf·L_return·I_dm, with I_dm = V/R_L or V·2πf·C_L.
  - Field: E_max = F_max·0.55·V_cm·boardfactor·cablefactor, with boardfactor = sin(2πL_eff/λ) for λ ≥ 4L_eff (else 1), and cablefactor = sin(2π·1 m/λ) for λ ≥ 4 m (else 1). F_max = 2/sin(√(c/(f·L_cable))) above the cable half-wave resonance. L_eff depends on which side(s) of the trace the selected cable connectors are on.
  - Assumptions: board not in a shielded enclosure; cable much longer than the board; about 1 m above a ground plane. References are Su & Hubing 2011 (IEEE T-EMC 53(1) and 53(4)) and Zhu & Hubing CVEL-13-051 (2013).
- **Clemson expert system / MREMC lineage.** Every radiated EMI problem needs a source, a coupling path and an antenna, and "each combination can be readily identified by a computer with access to both the board layout and component information." [S] — [Clemson CVEL MREMC project](https://cecas.clemson.edu/cvel/Projects/cvel_proj_MREMC.html)
- **Ott, cable common-mode current.** "The radiation from a cable is directly proportional to the common-mode current on that cable." Measure with a clamp-on probe (F-33-1, 5 Ω transfer impedance, flat 2–250 MHz) and a spectrum analyser. "For a Class B product, the current must be less than 5 microamps (15 microamps for a Class A product)" for cables ≥1 m. Shorter cables scale up proportionally (0.5 m gives 10 µA for Class B). Iterate over all cables, because fixing one raises another. "The most useful" EMC measurement. [P] — [Ott, Common-Mode Current](https://hott.shielddigitaldesign.com/techtips/tips-cm.html)
- **Hartley.** "It takes as little as eight to ten microamps … of load current coupled into a balanced antenna to cause an FCC Class B radiated emissions failure." [P] — [Altium OnTrack podcast transcript](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley)
- **FCC §15.109(a) Class B radiated limits at 3 m:** 30–88 MHz 100 µV/m; 88–216 MHz 150 µV/m; 216–960 MHz 200 µV/m; >960 MHz 500 µV/m. Class A at 10 m: 90 / 150 / 210 / 300 µV/m. [P] — [47 CFR 15.109](https://www.law.cornell.edu/cfr/text/47/15.109)
- **Formulas cited to Ott's *EMC Engineering* Ch. 6.** Differential-mode loop: E = 2.632×10⁻¹⁴·f²·A·I/r (V/m, with ground-plane image). Common-mode cable: E = 1.257×10⁻⁶·f·L·I_CM/r. Scaling: 2× loop area gives +6 dB; 2× frequency gives +12 dB (differential mode). [P-code, secondary to Ott's book] — [kicad-happy emc-precompliance.md](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md)
- **Board cavity resonance:** f_mn = (c/(2√εr))·√((m/L)² + (n/W)²), independent of plane spacing (which must be ≪ L, W). Fringing lowers it slightly. [P] — [LearnEMC Cavity Resonance Calculator](https://learnemc.com/ext/calculators/cavity_resonance/pcb-res.html)

#### Connectors, edges, stitching, grounding
- **LearnEMC (good guidelines):**
  - Connectors on one edge or corner. If unavoidable, "avoid placing high-frequency circuits between any two connectors," or use a metal enclosure with filtering to chassis.
  - A device that communicates off-board through a connector should be "within 2 cm" of it.
  - All off-board communication from one device should go through one connector.
  - Components not on I/O nets should be "at least 2 cm away from I/O nets and connectors" (2 cm being situational).
  - "No trace unrelated to I/O should be located between an I/O connector and the device(s) sending and receiving signals using that connector."
  - "Signals with high-frequency content should not be routed beneath components used for board I/O."
  - "Critical nets should be routed at least 2X from the board edge, where X is the distance between the trace and its return current path."
  - Use as few vias as possible in high-frequency nets.
  
  [P] — [LearnEMC, Good EMC Design Guidelines](https://learnemc.com/other-good-emc-design-guidelines)
- **LearnEMC (worst guidelines).**
  - The I/O ground separated from digital ground with one connection point is "one of the worst possible ways." The goal is low-impedance chassis-to-digital-ground bonding above 30 MHz and isolation below about 100 kHz. Achieve this with chassis ground on a separate layer *overlapping* digital ground, bonded by multiple low-inductance SMT capacitors, plus one low-frequency connection where it makes most sense.
  - A digital-to-chassis connection at the oscillator is "more often than not … a bad idea."
  - "If the ground plane needs to be cleared out of a particular area (e.g., under magnetics, power inverters, or for high-voltage isolation), that is often fine. Splitting/gapping a ground plane, however, is almost always a bad idea."
  
  [P] — [LearnEMC, Some of the Worst EMC Design Guidelines](https://learnemc.com/some-of-the-worst-emc-design-guidelines)
- **LearnEMC (worst guidelines)** on gapping a solid plane between analog and digital: valid only when <100 kHz noisy currents must be kept off a return shared with a circuit sensitive to currents about 3 orders of magnitude lower. Even then, "it is almost always better to provide separate return paths … using a trace or plane on a different board layer." [P] — [LearnEMC, Worst Guidelines](https://learnemc.com/some-of-the-worst-emc-design-guidelines)
- **Ott, mixed signal.** One ground plane, partitioned into analog and digital sections, with strict routing discipline on all layers. Digital return current "has no desire to flow through the analog portion." If split, bridge at one point and route every crossing trace over the bridge.
  - LSB voltage with a 1 V reference: 8 bit = 4 mV, 10 bit = 1 mV, 12 bit = 240 µV, 14 bit = 60 µV, 16 bit = 15 µV.
  - A single partitioned plane suffices for 8–12-bit converters. For ≥14 bit, use isolated analog regions still solidly connected under each converter: "the ground plane is not split." No trace crosses the isolating slots.
  - Suggested experiment: split with 0 Ω jumpers every ½", then compare.
  
  [P] — [Ott, Grounding of Mixed Signal PCBs](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html)
- **LearnEMC (not-so-good):** "use ground vias around the perimeter … every 2 cm to form a Faraday cage." Most boards with two or more ground planes have enough natural vias. Where they do not, "placing the vias around the outer edge of the board will create a resonant cavity … it is better to distribute these connections throughout the board." [P] — [LearnEMC, Not-So-Good Guidelines](https://learnemc.com/not-so-good-emc-design-guidelines)
- **Ott's** best 4-layer (G/S/S/G) stitches the two ground planes "around the periphery of the board to enclose all the signal traces in a faraday cage." [P] — [Ott Part 2](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-2.html)
- **Ott's red flags** in a digital design:
  - clock rise/fall times <10% of the clock period;
  - apertures >λ/20 (6" at 100 MHz);
  - split ground planes;
  - slots in planes crossed by traces;
  - pigtail shield terminations;
  - connector backshells not contacting the enclosure;
  - paint in enclosure seams;
  - signal layers not adjacent to a plane;
  - multiple-value parallel decoupling capacitors;
  - ungrounded copper fill or thieving;
  - unshielded I/O cables without common-mode filtering;
  - a single-point connection between circuit ground and chassis.
  
  [P] — [Ott, Red Flags](https://hott.shielddigitaldesign.com/techtips/red_flags.html)
- **Ott, "maximize emission" (a satirical inverted checklist, so invert each item for the design rule):**
  - fast edges (<1 ns) and high clock frequencies;
  - long clock runs far from planes, along the board edge and through the I/O area;
  - slots in planes;
  - clock traces across isolated grounds with the single point at the power supply;
  - one decoupling capacitor per IC, or fewer;
  - no I/O filters, or filters far from the cable entry with large parasitics;
  - long pigtails;
  - logic ground bonded to chassis at the edge *farthest* from the I/O;
  - painted seams;
  - the AC filter mounted far from the cord entry.
  
  "You should be able to increase the emission from your product by at least 20 to 30 dB." [P] — [Ott, Maximizing Emission](https://hott.shielddigitaldesign.com/techtips/maxemission.html)
- **Trace near the PCB edge:** common-mode current rises as the trace approaches the edge; a guard band of plane copper along the edge was the most effective suppression. [S] — [ResearchGate: CM current due to a trace near a PCB edge](https://www.researchgate.net/publication/3056626_Common-Mode_Current_Due_to_a_Trace_Near_a_PCB_Edge_and_Its_Suppression_by_a_Guard_Band)
- **20-H rule.** In Hubing and Shim's measurements, "although the near fields are more contained, the radiation from a board implementing the 20-H rule is actually slightly higher." [P, abstract] — [Hubing & Shim, 20-H Rule Modeling and Measurements (IEEE EMC 2001)](https://scholarsmine.mst.edu/ele_comeng_facwork/1333/)
- **LearnEMC.** A smaller power plane "does not reduce the radiation from the planes unless the power plane is sandwiched between two ground planes," and if fringing reduction is wanted, "2-H or 3-H is generally more than adequate." [P] — [LearnEMC, Worst Guidelines](https://learnemc.com/some-of-the-worst-emc-design-guidelines)

#### Filtering, ESD, ferrites, I/O
- **LearnEMC design review.** I/O nets "ideally … terminate in a series component near the connector." If an I/O net connects directly to an IC, make sure the IC cannot drive it with more than about 1 mV of common mode; otherwise filter or protect it. Mount filters to minimise parasitics and bypass coupling; avoid higher-order filters that ring. A CMC must filter a *balanced* pair. Never put a ferrite on a ground connection, and remove ferrites from ground or single-ended returns.
  
  Transient protection protecting an IC input connects to the IC ground; protection for the board connects to the EMC ground. Connection inductance is critical, and the protector must turn on faster than the part can be damaged. In metal enclosures, route ESD current to the enclosure "without being pulled too far onto the board." In plastic enclosures, look for arc paths through seams, and use resistors to slow high-impedance digital inputs. [P] — [LearnEMC, PCB Layout](https://learnemc.com/pcb-layout)
- **TI SLVA680.** TVS close to the ESD source, with the IC farther away; no stub on the protected line; TVS ground inductance is the dominant parasitic. [S] — [TI SLVA680](https://www.ti.com/lit/pdf/slva680)
- **emcvisual** implements ESD placement as "the diode is not closer to the connector pin than to the nearest IC pin of the line," or its ground pad has no pour or via within 2 mm. It implements filter placement as a ferrite, inductor or shunt capacitor on a cable line more than 10 mm from the connector pin (citing TI SLVA680, Wyatt). [P-code] — [emcvisual RULES.md](https://github.com/tombueng/emcvisual/blob/main/docs/RULES.md)
- **Johnson, clock modulation.** Spread-spectrum clocking really does lower peak readings when the new spectral lines are more than 100 kHz apart (the measurement bandwidth), but it is unsuitable as a reference for transceivers, PLL CPUs and RF. He prefers planes, small trace-to-plane spacing, slower edges, differential and low-swing clocks. [P] — [Johnson, "Intentional Clock Modulation"](https://www.sigcon.com/Pubs/edn/clockmod.htm)

#### Pre-compliance and design-review practice
- **LearnEMC's ten-step PCB EMC design review:**
  1. ground structure and I/O locations;
  2. ground plane layers and extent (no gaps);
  3. ground traces or fills on other layers (remove);
  4. power distribution (<0.25 mm plane pair when ≥3 power pins at a voltage);
  5. I/O nets (series component near connector; ≤1 mV common mode);
  6. filters (mounting, ringing, ferrite suitability, CMC on balanced pairs);
  7. traces needing transition-time control (default series R);
  8. critical components (inductors, op-amp loops over a solid plane, transient protection grounding, PLL supply ferrites, never a ferrite on ground);
  9. power inverters (minimise switch-node area, keep it away, watch loops, consider shielded parts);
  10. each compliance test's current path (conducted emissions, radiated emissions, BCI, radiated immunity, EFT, ESD).
  
  "In these situations, mounting pads and clearances can be incorporated in the design to allow for filtering, transient protection, or shielding in the event that it is necessary." [P] — [LearnEMC, PCB Layout](https://learnemc.com/pcb-layout)
- **LearnEMC.** "Blindly adhering to a list of EMC design rules is not likely to result in an EMC-compliant design. The best strategy … involves identifying and quantifying possible sources, victims, and coupling paths." Hold the EMC design review *before the first layout* and again "as soon as the first draft of the board layout is available." The "Design for Guaranteed EMC Compliance" method combines modelling with targeted guidelines. [P] — [LearnEMC, PCB Layout](https://learnemc.com/pcb-layout); [LearnEMC, Effective Application](https://learnemc.com/effective-application-of-emc-design-guidelines); [LearnEMC, Why Be Cautious](https://learnemc.com/why-you-should-be-cautious-about-using-emc-design-guidelines)
- **Johnson, on EMI simulation tools:** "Real, live EMI problems are much too complex for even the best software tools." Rules: (1) limit rise times; (2) use experience: "If last year's design was X, and today we are planning to do 2x, we will need another 6dB of protection"; (3) "Run an EMI preview scan as early as possible." "The most promising new EMI tools are more like expert systems than simulators." [P] — [Johnson, "EMI Simulation Tools"](https://www.sigcon.com/Pubs/edn/emisim.htm)
- **Ott.** Ask the fabricator to etch but not laminate one set of boards, so buried planes can be inspected for slots. [P] — [Ott, Slots](https://hott.shielddigitaldesign.com/techtips/tips-slots.html)
- **kicad-happy pre-compliance outputs (MIT):** frequency-band prioritisation by number of emission sources (clock and switching harmonics); interface risk ranking by protocol speed and filter or ESD presence; XY probe points (switching inductors, crystals, unfiltered connectors) for near-field scanning; a 0–100 risk score with at most 3 findings counted per rule. [P-code] — [kicad-happy emc-precompliance.md](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md)

#### Rule table
| ID | Rule | Numeric | Why | Applies when | Sev | Check | Source |
|---|---|---|---|---|---|---|---|
| EMI-1 | All cabled connectors on one edge or corner | Cluster test (§11) | Avoid voltage between antenna parts | ≥2 cabled connectors, no bonded metal chassis | P1 | G | [LearnEMC](https://learnemc.com/the-most-important-emc-design-guidelines) [P] |
| EMI-2 | No high-speed circuitry or traces between connectors (or plan a chassis bond at both) | Estimated V_cm < 1 mV (Class B) or < 100 µV (stricter) | Plane flux gives mV between cable references | Same | P0/P1 | G (MREMC-style estimate) | [LearnEMC](https://learnemc.com/pcb-layout) [P]; [CMode_algr.js](https://learnemc.com/ext/calculators/mremc/calculator/CMode_algr.js) [P-code] |
| EMI-3 | I/O devices within about 2 cm of their connector; non-I/O parts ≥2 cm from I/O; no unrelated traces between connector and its device; no fast signals under I/O parts | 2 cm (situational) | Short I/O; avoid coupling onto I/O | Cabled I/O | P1 | G / K (rule areas) | [LearnEMC](https://learnemc.com/other-good-emc-design-guidelines) [P] |
| EMI-4 | Critical nets ≥2X from the board edge (X = height to return plane); centreline ≥ w/2 + 3h from any plane edge | 2h–3h | Edge field containment | All fast nets | P1 | K (`edge_clearance` per class and layer) / G (plane edges) | [LearnEMC](https://learnemc.com/other-good-emc-design-guidelines) [P]; [Adamczyk](https://incompliancemag.com/pcb-return-current-distribution-in-a-microstrip-line/) [P] |
| EMI-5 | Transition time ≈20% of bit period; default series R on capacitive loads | t_r ≈ 0.2·UI | Harmonics above the knee | Digital | P1 | G | [LearnEMC](https://learnemc.com/the-most-important-emc-design-guidelines) [P] |
| EMI-6 | No splits or gaps in the return plane; clear-outs under magnetics or HV are OK; one partitioned plane for mixed signal | n/a | Detours, conducted CM drive | All | P0 | G | [LearnEMC](https://learnemc.com/some-of-the-worst-emc-design-guidelines) [P]; [Ott](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html) [P] |
| EMI-7 | Apertures and unstitched spans < λ/20 at the highest frequency of concern (Ott red flag); distribute GND-GND stitching throughout, not only at the perimeter | λ/20 (6" at 100 MHz) | Slot antennas; cavity resonance | Multi-GND-plane boards | P1 | G (largest-empty-circle, §11) | [Ott](https://hott.shielddigitaldesign.com/techtips/red_flags.html) [P]; [LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines) [P] |
| EMI-8 | Chassis to digital ground: high-frequency bond with multiple SMT capacitors on an overlapping chassis layer, plus one low-frequency connection; never a single point at the I/O by default, never at the oscillator | n/a | Low impedance above 30 MHz, isolation below 100 kHz | Products with chassis | P1 | G | [LearnEMC](https://learnemc.com/some-of-the-worst-emc-design-guidelines) [P]; [Ott](https://hott.shielddigitaldesign.com/techtips/red_flags.html) [P] |
| EMI-9 | I/O nets end in a series or filter component near the connector; protection grounding chosen (IC ground versus EMC ground); no ferrite on ground | n/a | Block or divert common mode and transients | All I/O | P1 | G | [LearnEMC](https://learnemc.com/pcb-layout) [P] |
| EMI-10 | Footprints for optional filters, transient protection and shield cans where compliance is uncertain | n/a | Cheap insurance before prototypes | Uncertain designs | P2 | G (placeholder presence) | [LearnEMC](https://learnemc.com/pcb-layout) [P] |
| EMI-11 | No floating copper; ground fill only on 2-layer boards, tied with many vias | n/a | Floating metal can resonate; fill without vias is ineffective | All | P2 | G | [Ott](https://hott.shielddigitaldesign.com/techtips/red_flags.html) [P]; [HyperLynx](https://schematicsforfree.com/files/Manufacturing%20and%20Design/PC%20Board%20Design%20and%20Fabrication/PCB%20Design,%20Layout%20&%20Routing/USING%20HYPERLYNX%20DRC%20TO%20FIND%20EMI%20ISSUES.pdf) [P] |
| EMI-12 | Pre-compliance: review before layout and after first draft; clamp-measure every cable to <5 µA (Class B, ≥1 m) | 5 µA B / 15 µA A | E ∝ I_CM | Prototype | P1 | lab | [Ott](https://hott.shielddigitaldesign.com/techtips/tips-cm.html) [P]; [LearnEMC](https://learnemc.com/effective-application-of-emc-design-guidelines) [P] |

### Inferences
- **Consistency check, using Ott's common-mode formula as cited by kicad-happy and the FCC limit:** at 100 MHz, a 1 m cable and r = 3 m, the Class B limit of 150 µV/m gives I = E·r/(1.257×10⁻⁶·f·L) ≈ 3.6 µA. That is consistent with Ott's 5 µA rule and Hartley's 8–10 µA (different geometry assumptions).
- **Consistency check with the MREMC model:** V_cm = 1 mV gives E ≈ 0.55 × 2 × 1 mV ≈ 1.1 mV/m (≈61 dBµV/m) near cable resonance, about 20 dB over the Class B limit. That explains why Hubing's 1 mV threshold is a hard line and 100 µV is needed for stricter limits.
- The perimeter-stitching debate (Ott: periphery Faraday cage on G/S/S/G; LearnEMC: perimeter-only rings can form a cavity, so distribute) reconciles into one checker. Measure the *largest unstitched region anywhere* between the two ground planes, not just the edge pitch (§11).

### Gaps
- The Clemson MREMC technical reports (CVEL-13-051/052) and Hubing's "PCB EMI Source Mechanisms" paper could not be read because of the server's TLS chain problem. The algorithm above is from the live calculator code.
- No primary source quantifies TVS and CMC distances. The vendor numbers from the first pass are [S], and the rule-pack agent is verifying them.

---

## 8. Placement priorities driven by SI/EMI

### Takeaway
Fix connectors first, clustered on one edge or corner. Place each interface's protection, filtering and magnetics at the connector, and the interface IC within about 2 cm. Place critical ICs so that high-speed paths are short, uncrossed, and do not pass between connectors. Place clock sources next to their single consumer, away from I/O and edges. Partition the rest by *function and signal path*, not by blanket type-versus-connector rules, over one continuous ground.

### Cited Findings
- **LearnEMC's worst guideline:** "Circuits … grouped by type, with power circuits closest to the connector and high-speed digital circuits farthest from the connector" is "probably responsible for more crazy board layouts than any other." It ignores function, and it has produced "very high-speed digital signals routed all the way across the board in an attempt to keep the digital components away from the connector." Usually it is better to "put the components that send or receive signals through the connector nearest the connector." This resolves the first-pass conflict with a vendor blog that advocated grouping by speed. [P] — [LearnEMC, Worst Guidelines](https://learnemc.com/some-of-the-worst-emc-design-guidelines)
- **LearnEMC:** connectors on one edge or corner; I/O device within about 2 cm of its connector; one connector per device's off-board links; non-I/O parts ≥2 cm from I/O; clock driver adjacent to oscillator; exclusive communicators placed together. [P] — [LearnEMC, Good Guidelines](https://learnemc.com/other-good-emc-design-guidelines)
- **Johnson.** Place ICs so a differential pair leaves the driver in the same direction it enters the receiver, which cancels turn skew. [P] — [Johnson, "Skewed Layout"](https://www.sigcon.com/Pubs/edn/SkewedLayout.htm)
- **Ott.** Partition mixed-signal boards with routing discipline on all layers; ADCs at the partition. [P] — [Ott mixed signal](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html)
- **LearnEMC.** Switch nodes: minimise area and keep away from conductors that could carry noise; watch switching-loop magnetic coupling. Modern DC-DC converters should switch in the MHz range and should not have isolated power grounds. [P] — [LearnEMC, PCB Layout](https://learnemc.com/pcb-layout)
- **emcvisual thresholds (rules with stated origins):** crystal ≥5 mm from the edge and ≥10 mm from cable connectors; storage inductor ≥3 mm from the edge and ≥10 mm from cable connectors; switch-node copper <100 mm² (<40 mm² near an edge or connector); hot loop flagged from 30–40 mm². [P-code] — [emcvisual RULES.md](https://github.com/tombueng/emcvisual/blob/main/docs/RULES.md)

#### Placement priority order (machine-actionable)
| Step | Action | Rule source |
|---|---|---|
| 1 | Lock mechanical items; cluster cabled connectors on one edge or corner; mark the I/O zone | [LearnEMC](https://learnemc.com/the-most-important-emc-design-guidelines) [P] |
| 2 | Place per-connector protection, filters, CMC, magnetics and shield or chassis bond inside the I/O zone, immediately at the pins | [LearnEMC](https://learnemc.com/pcb-layout) [P] |
| 3 | Place the interface ICs within about 2 cm of their connector; keep the corridor free of unrelated traces | [LearnEMC](https://learnemc.com/other-good-emc-design-guidelines) [P] |
| 4 | Place critical ICs (SoC/FPGA, DRAM in fly-by order, SerDes) so fast links are short, uncrossed, entry and exit directions aligned, and never between two connectors | [LearnEMC](https://learnemc.com/the-most-important-emc-design-guidelines) [P]; [Johnson](https://www.sigcon.com/Pubs/edn/SkewedLayout.htm) [P] |
| 5 | Place clocks next to their consumer, away from the I/O zone and edges | [LearnEMC](https://learnemc.com/other-good-emc-design-guidelines) [P] |
| 6 | Partition analog / digital / power by function over one plane; power stages with small switch nodes, away from I/O | [Ott](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html) [P]; [LearnEMC](https://learnemc.com/pcb-layout) [P] |
| 7 | In-line SI parts (series R at the driver, AC caps on the TX leg), then decoupling and passives | [LearnEMC](https://learnemc.com/pcb-layout) [P] |

### Inferences
- Steps 1–3 are hard, anchor-relative constraints. Steps 4–6 are soft objectives in a placer cost: fast-net length, crossing count, "between-connectors" penalty from the MREMC-style estimate (§11 algorithm F), I/O-zone intrusion, and edge proximity.

### Gaps
- No primary source prescribes a numeric weighting of these placement objectives.

---

## 9. Myths and context-dependent rules of thumb

### Takeaway
Several famous rules are wrong in general or valid only in narrow contexts. The physics behind each should be encoded, never the slogan.

### Cited Findings
| Rule | Verdict | Primary evidence | Source |
|---|---|---|---|
| 90° corners | Electrically negligible in digital work up to about 2 Gb/s. For an 8 mil, 50 Ω FR-4 microstrip: about 1 ps delay, 0.012 pF excess capacitance, about 0.3% reflection at a 100 ps edge. Rounding removes 21% of corner copper, but 70–90% would be needed to neutralise the capacitance. Corners begin to matter around 10 Gb/s and for diff-pair skew. LearnEMC calls it an "urban legend" with "no advantage" to two 45° turns | Johnson; LearnEMC | [Johnson, Big Bad Bend](https://www.sigcon.com/Pubs/edn/bigbadbend.htm) [P]; [LearnEMC Worst](https://learnemc.com/some-of-the-worst-emc-design-guidelines) [P] |
| 20-H rule | Measured far-field radiation slightly *higher*. It only helps when power is sandwiched between grounds; 2-H or 3-H suffices for fringing | Hubing & Shim; LearnEMC | [Scholars' Mine abstract](https://scholarsmine.mst.edu/ele_comeng_facwork/1333/) [P]; [LearnEMC Worst](https://learnemc.com/some-of-the-worst-emc-design-guidelines) [P] |
| Split analog/digital ground | "Probably a close second" worst guideline. Valid only for <100 kHz isolation at about 1000:1 sensitivity, and better done with separate return paths on another layer | LearnEMC; Ott; Bogatin | [LearnEMC Worst](https://learnemc.com/some-of-the-worst-emc-design-guidelines) [P]; [Ott](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html) [P]; [Bogatin](https://www.teledynelecroy.com/oscilloscope/blog/signal-return-paths-signal-and-power-integrity-tutorial/) [P] |
| I/O ground island with single-point tie | "One of the worst possible ways." Use an overlapped chassis layer with capacitors | LearnEMC; Ott | [LearnEMC Worst](https://learnemc.com/some-of-the-worst-emc-design-guidelines) [P]; [Ott red flags](https://hott.shielddigitaldesign.com/techtips/red_flags.html) [P] |
| Group circuits by type, high-speed farthest from connector | "Responsible for more crazy board layouts than any other" | LearnEMC | [LearnEMC Worst](https://learnemc.com/some-of-the-worst-emc-design-guidelines) [P] |
| 3W rule | Proxy for D/H. K = 1/(1+(D/H)²); s = 4h (microstrip) or 2h (stripline) gives <2% | Johnson; Ott | [Johnson](https://www.sigcon.com/Pubs/news/2_13.htm) [P]; [Ott](https://hott.shielddigitaldesign.com/techtips/rulesofthumb.html) [P] |
| Guard traces | Little benefit on boards with planes; use only for a specific known problem; ground at both ends | Johnson; LearnEMC | [Johnson](https://www.sigcon.com/Pubs/news/15_02.htm) [P]; [LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines) [P] |
| Ground fill on multilayer | No function; perturbs impedance. Floating fill is an Ott red flag | Johnson; Ott | [Johnson](https://www.sigcon.com/Pubs/edn/GroundFill.htm) [P]; [Ott](https://hott.shielddigitaldesign.com/techtips/red_flags.html) [P] |
| Perimeter ground vias every 2 cm as a Faraday cage | Usually unnecessary; a perimeter-only ring can form a resonant cavity, so distribute (but Ott does stitch the periphery on G/S/S/G) | LearnEMC; Ott | [LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines) [P]; [Ott P2](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-2.html) [P] |
| Two ground planes required above 25 MHz | Outdated; many GHz boards use one | LearnEMC | [LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines) [P] |
| Terminate every trace longer than λ/4 | Relate delay to t_r; slow edges first | LearnEMC; Johnson | [LearnEMC Worst](https://learnemc.com/some-of-the-worst-emc-design-guidelines) [P]; [Johnson](https://www.sigcon.com/Pubs/news/3_14.htm) [P] |
| Series R required above 1 V/ns; source Z ≥ Z0/4 for capacitive loads | "Never one of them" (not decision criteria) | LearnEMC | [LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines) [P] |
| Single-point for low frequency / multipoint for high frequency | Misused; control low-frequency current by limiting options, and high-frequency current by providing one good option | LearnEMC | [LearnEMC Worst](https://learnemc.com/some-of-the-worst-emc-design-guidelines) [P] |
| Minimise all high-speed trace lengths | Not an EMC fix by itself; "control your loop areas" | LearnEMC | [LearnEMC PCB Layout](https://learnemc.com/pcb-layout) [P] |
| Rely on slow logic for EMC | Dangerous: parts get faster over production life; use slew-controlled logic | LearnEMC | [LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines) [P] |
| Ferrite in a ground or return path | Never | LearnEMC | [LearnEMC Most Important](https://learnemc.com/the-most-important-emc-design-guidelines) [P] |
| Fixed decoupling values (0.1 µF ≤15 MHz, 0.01 µF above) | Depends on plane spacing; dangerous as a general rule | LearnEMC | [LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines) [P] |
| Decoupling caps on both sides of a plane gap | "Don't gap the ground plane!" | LearnEMC | [LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines) [P] |
| Ground daughterboards to chassis, not via connector grounds | "Don't confuse current return paths with grounds"; signal currents should return on connector pins | LearnEMC | [LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines) [P] |
| Chamfered or rounded diff-pair corners remove skew | No (1.57p–2p per corner regardless) | Johnson | [Johnson](https://www.sigcon.com/Pubs/edn/SkewedLayout.htm) [P] |
| Tighter diff-pair coupling always reduces EMI | Not below about 0.5 mm; driver imbalance dominates | Johnson | [Johnson](https://www.sigcon.com/Pubs/edn/ReducingEMI.htm) [P] |
| Following as many EMC guidelines as possible | "A board that complies with 90% of the guidelines may be much worse than a board that complies with only one or two" | LearnEMC | [LearnEMC Why Cautious](https://learnemc.com/why-you-should-be-cautious-about-using-emc-design-guidelines) [P] |

### Inferences
- In the knowledge base, each myth row should be a *negative rule*: a record that blocks the LLM from emitting the slogan as a constraint, and that carries the physics-based replacement check.

### Gaps
- Archambeault's own 20-H publications were not retrieved; the 20-H verdict rests on Hubing and Shim plus LearnEMC.

---

## 10. Authoritative sources and their key claims

### Takeaway
The primary authors agree on one physical model: energy in fields, current in the least-inductance loop, and EMI from voltage between antenna parts. Their quotable, encodable rules are listed below with provenance.

### Cited Findings
- **Henry Ott** [P]:
  - four stackup factors and five objectives; 8 layers is the minimum for all five, and >8 layers is only for routing;
  - 4-layer gives 15 dB less radiation than 2-layer;
  - signal-to-plane <0.010" with core >0.040" on 4-layer; 0.005" gives ≥10 dB less trace-loop radiation; crosstalk ∝ h²;
  - routing preference order 1–4 for layer changes; stitching caps 0.001–0.01 µF within 0.1" (5–10 nH); a plane has two surfaces above 30 MHz;
  - slot measurements; one partitioned ground plane, with LSB table;
  - rules of thumb (Z0, delays, s = 4h or 2h, stub = t_r); twelve red flags;
  - common-mode current <5 µA (Class B) or <15 µA (Class A) measured with a clamp;
  - satirical "maximize emission" list (20–30 dB).
  
  — [Ott tech tips](https://hott.shielddigitaldesign.com/techtips/index.html)
- **Todd Hubing / LearnEMC** [P]:
  - source, antenna and coupling framework; three antenna conditions; 1 mV between antenna parts (100 µV for stricter standards);
  - four most important guidelines (loop areas, no split return planes, no high-speed between connectors, transition times ≈20% UI);
  - ten-step design review; good, not-so-good and worst guideline lists;
  - 20-H measurements; MREMC common-mode algorithm (live calculator code); list of commercial EMC rule checkers.
  
  — [LearnEMC EMC design guidelines hub](https://learnemc.com/emc-design-guidelines); [LearnEMC PCB Layout](https://learnemc.com/pcb-layout)
- **Eric Bogatin**:
  - [P] lowest loop impedance and current-filament model; split-plane trifecta; the only split benefit is low-frequency resistive coupling with the gap parallel to the signals; Rule #7: continuous adjacent return path for every signal.
  - [S] 2W gives about 2.5% NEXT; FEXT ≈ 0.5%·Len/RT; quarter-wave stub ≈ 1.5 GHz·in; stubs < 0.3/Gbps (reported by Telian [P]).
  
  — [Teledyne LeCroy](https://www.teledynelecroy.com/oscilloscope/blog/signal-return-paths-signal-and-power-integrity-tutorial/); [SIJ 20 rules](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers)
- **Howard Johnson** [P]:
  - K = 1/(1+(D/H)²) (with saturation and aggressor sum); crosstalk ∝ H²/D²;
  - guard traces and ground fill useless with planes;
  - right-angle bends negligible to about 2 Gb/s (1 ps, 0.012 pF, 0.3%);
  - critical length 1/10–1/3 t_r, simulate >1/6;
  - 20% skew → 10% CM; corner skew 1.57p–2p; same-direction rule; 0.5 mm diff spacing enough for EMI;
  - serpentine switchback < ⅓ t_r; 10:1 signal-to-ground via ratio (3-D scaling);
  - differential pairs return under each leg; XFP differential-via ground pattern;
  - spread-spectrum clock caveats; "run an EMI preview scan early."
  
  — [Signal Consulting EDN article index](https://www.sigcon.com/Pubs/edn/)
- **Rick Hartley** [P]:
  - energy in the dielectric; 100% of the return in the adjacent plane;
  - never two signal layers on one plane, never stacked power planes without ground;
  - rejects thick S/P/G/S 4-layer and S/P/S/S/G/S 6-layer; disowned his older stack-up paper;
  - 8–10 µA → Class B failure; problems track rise time, not clock.
  
  — [Altium OnTrack transcript](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley); [EEJournal](https://www.eejournal.com/article/matters-of-integrity/)
- **Bruce Archambeault** [P]:
  - termination choice changes harmonic current by 10–20 dB, so choose for minimum current;
  - reference-plane changes magnify stray (common-mode) current;
  - creator of IBM's EMSAT rule checker ("hundreds of man-years" of IBM expertise [S]).
  - Bogatin quotes him: "engineering" is "Geek for 'tradeoff analysis.'"
  
  — [Archambeault, "Reducing Emissions"](https://www.sigcon.com/Pubs/edn/ReducingEmissions.htm); [Bogatin 20 rules](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers); [LearnEMC rule checkers](https://learnemc.com/commercial-emc-rule-checkers)
- **Donald Telian** [P]: stubs < 0.3/Gbps (Bogatin's rule) explained; pad rings count; connector pad entry direction; 25+ Gb/s needs SMT connectors. — [SIJ](https://www.signalintegrityjournal.com/articles/2962-fixing-the-problem-of-stubs)
- **Bogdan Adamczyk** [P]: return-current spread (±1h 50%, ±3h 80%, ±10h 97% microstrip; ±3h 99% stripline). — [In Compliance](https://incompliancemag.com/pcb-return-current-distribution-in-a-microstrip-line/)
- **TI SPRAAR7J** [P]: 1.5 W, 5 W, 200 mil stitching vias, ≤1 µF split stitching caps, 15 mil stubs, no overlapping non-referencing planes. — [TI](https://www.ti.com/lit/pdf/spraar7)
- **Lee Ritchey**: no primary material retrieved.

### Inferences
- **Knowledge-base tags:** `source_author`, `source_type ∈ {physics, rule-of-thumb, vendor-req, spec-req, measured, satirical-inverse}`, `provenance ∈ {P, P-code, S}`, `confidence`. Spec and vendor requirements override rules of thumb, and physics drives the checkers.

### Gaps
- Ritchey's *Right the First Time* and Ott's and Johnson's books were not accessed directly.

---

## 11. KiCad-encodable constraints versus geometric/physics checks: algorithms and open-source implementations

### Takeaway
- **KiCad 9/10 native:** widths, clearances, diff-pair gap and uncoupled length, `skew` (vs. longest net, `within_diff_pairs`), `length`, `via_count`, `edge_clearance`, `track_angle`, `track_segment_length`, `assertion`, and area-scoped rules.
- **KiCad 10 adds:** time-domain (delay) tuning with per-layer and via unit delays, and backdrill modelling.
- **KiCad master (unreleased) adds:** `return_path`, a polygon test that the net-chain copper is covered by zone fill on a named reference layer; `stub_length` and `net_chain_length` for multi-net "net chains"; and a via-stitch generator with STITCH and GUARD modes.
- **Still not native:** automatic per-layer reference detection from the stackup; detour-length and island analysis over voids; reference-change bridging (stitching via or cap proximity); loop area; via stub length; crosstalk coupled length; connector clustering and "between connectors"; and stitching density. Open-source Python implementations of most of these exist (licences vary).

### Cited Findings

#### KiCad native capability (primary)
- **KiCad 9 constraint table** includes `assertion`, `diff_pair_gap`, `diff_pair_uncoupled`, `edge_clearance`, `length` ("also sets a target length … used by the length tuning tool"), `skew` (min/opt/max/`within_diff_pairs`; difference from the longest matched net), `track_angle`, `track_segment_length` and `via_count` (min/max).
- **KiCad 9 example rules use** `A.hasNetclass()`, `A.inDiffPair('/CLK')`, `A.inDiffPair('*') && !AB.isCoupledDiffPair()`, `A.intersectsArea('zone3')`, `A.intersectsCourtyard('U3')` and `memberOfSheet()`/`memberOfSheetOrChildren()` (the latter added in 9.0.2).

[P] — [KiCad 9.0 PCB Editor docs](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html)
- **KiCad 10 time-domain tuning.** Delay = Σ(track length × per-layer unit delay) + via delay (via height from stackup × via unit delay, with per-layer-pair overrides) + pad-to-die delay. Configured in tuning profiles, with targets in ps. Recommended for DDR, PCIe and USB "even if your design appears to have all traces on one layer." KiCad 10 also models backdrills on vias and pads. [P] — [KiCad 10.0 PCB Editor docs](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html)
- **KiCad master, new keywords** (vs 10.0): `return_path`, `stub_length`, `net_chain_length`, `hole_aspect_ratio`, `microvia_stack_depth`, `net`. [P-code] — [common/drc_rules.keywords](https://gitlab.com/kicad/code/kicad/-/raw/master/common/drc_rules.keywords)
- **KiCad master `return_path`.** Syntax `(constraint return_path (layer "B.Cu") (net "GND"))`, with an optional net wildcard. Algorithm:
  1. Build the union of zone fills on the reference layer, filtered by net.
  2. For each track or arc of the net chain, convert to a polygon and `BooleanSubtract` the union.
  3. Treat any remainder as unreferenced copper.
  4. Coalesce adjacent flagged regions by union-find over polygon intersection.
  5. Report "Net chain '%s' has no copper return path on reference layer '%s'."
  
  It checks one explicit layer per rule. It does not check vias, detours, edge proximity or reference changes. [P-code] — [drc_rule_parser.cpp](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/drc/drc_rule_parser.cpp); [drc_test_provider_matched_length.cpp](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/drc/drc_test_provider_matched_length.cpp); [drc_item.cpp](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/drc/drc_item.cpp)
- **KiCad master net chains.** Nets carry a chain name (`GetNetChain()`). Chain length and delay include "bridging" across series components (`BoardChainBridging`). A chain topology yields trunk length and delay plus stubs (branch point, length, delay), and `stub_length` is time-domain capable. [P-code] — [drc_test_provider_matched_length.cpp](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/drc/drc_test_provider_matched_length.cpp)
- **KiCad master `PCB_VIA_STITCH` generator.** Modes: STITCH (fill an outline with vias) and GUARD ("place vias to guard a net", walking the guarded net's envelope). Layouts: PLAIN, STAGGERED, POISSON. Default pitch = max(2 mm, 2 × via diameter). Exposed through the IPC API (`ViaStitchGuardSettings`). A DRC provider checks for overlapping same-net stitch zones. [P-code] — [pcb_via_stitch.h](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/generators/pcb_via_stitch.h); [pcb_via_stitch.cpp](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/generators/pcb_via_stitch.cpp); [drc_test_provider_via_stitch.cpp](https://gitlab.com/kicad/code/kicad/-/raw/master/pcbnew/drc/drc_test_provider_via_stitch.cpp)
- **KiCad IPC Python API (kipy).** `Board.get_stackup()`, `get_zones()`, `refill_zones()`, `get_pad_shapes_as_polygons()`, `hit_test()`; `Zone.filled_polygons` keyed by layer. [P-code] — [kipy board.py](https://gitlab.com/kicad/code/kicad-python/-/raw/main/kipy/board.py); [kipy board_types.py](https://gitlab.com/kicad/code/kicad-python/-/raw/main/kipy/board_types.py)
- **IPC limitations:** "KiCad's SWIG bindings don't expose the stackup, so it is parsed from the `.kicad_pcb` file" (return_path checker). "KiCad 10's public IPC does not expose stable custom DRC-marker creation" (EMI Guardian). [P] — [return_path README](https://github.com/jasonarnoldarnie/kicad-tools); [EMI Guardian README](https://github.com/hap231/kicad-emi-guardian)

#### Commercial and academic EMC rule checkers (for rule-set reference)
- **HyperLynx DRC EMI rules:** edge-rate-to-period ratio, edge shield, exposed length, filter placement, ICs over split, I/O coupling, metal island, net crossing a gap, net near a plane edge, vertical reference plane change, via stub length. "These rules are parameterized and customizable." [P] — [HyperLynx DRC EMI whitepaper](https://schematicsforfree.com/files/Manufacturing%20and%20Design/PC%20Board%20Design%20and%20Fabrication/PCB%20Design,%20Layout%20&%20Routing/USING%20HYPERLYNX%20DRC%20TO%20FIND%20EMI%20ISSUES.pdf)
- **LearnEMC's checker list:** EMISTREAM (NEC), HyperLynx DRC (Mentor), EMSAT (IBM; viewers in Pantheon and Simbeor), Zuken CR-8000 EMC Adviser EX. Net information comes from manual entry, net-name substrings ("+3v", "gnd", "clk"), net-classification algorithms with a component database, or IBIS and simulation import. [P] — [LearnEMC, EMC Design Rule Checkers](https://learnemc.com/commercial-emc-rule-checkers)

#### Open-source implementations (read from code)
| Project | Licence | Platform | What it checks (algorithm) | Source |
|---|---|---|---|---|
| jasonarnoldarnie/kicad-tools `return_path` | **None stated** (all rights reserved; read for algorithm only) | KiCad 10 bundled Python (pcbnew SWIG + numpy) | Details below | [README](https://github.com/jasonarnoldarnie/kicad-tools) [P]; [return_path_check.py](https://github.com/jasonarnoldarnie/kicad-tools/blob/main/return_path/return_path_check.py) [P-code] |
| aklofas/kicad-happy (EMC skill) | MIT | Python on analyser JSON; agent skill for Claude Code / Codex | 44 rule IDs in 18 categories; details below | [emc-precompliance.md](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md) [P]; [emc_rules.py](https://github.com/aklofas/kicad-happy/blob/main/skills/emc/scripts/emc_rules.py) [P-code] |
| hap231/kicad-emi-guardian | MIT | KiCad ≥10.0.5 IPC plugin (kicad-python) | Details below | [README](https://github.com/hap231/kicad-emi-guardian) [P]; [noise.py, quantitative.py, default-config.json](https://github.com/hap231/kicad-emi-guardian/tree/main/plugin) [P-code] |
| tombueng/emcvisual | 0BSD-style ("Permission to use, copy, modify, and/or distribute…") | Browser (TypeScript); reads KiCad 6–10, IPC-2581, ODB++, Eagle | Quasi-static magnetic near field (Biot–Savart with image currents); about 30 rules, each with threshold, origin and test board; details below | [README](https://github.com/tombueng/emcvisual) [P]; [RULES.md](https://github.com/tombueng/emcvisual/blob/main/docs/RULES.md) [P] |
| RolandWa/KiCAD_Custom_DRC ("EMC Auditor") | **Non-commercial proprietary** | KiCad action plugin, TOML rules | Via stitching (GND via within 2 mm of critical signal vias); decoupling within 3 mm; ground-plane continuity sampled every 0.5 mm with a 1 mm zone around the trace; trace-to-plane-edge and board-edge distance; 3W isolation; filter topology at connectors; clearance and creepage (IEC 60664-1) | [README](https://github.com/RolandWa/KiCAD_Custom_DRC) [P] |
| easyw/RF-tools-KiCAD | GPL-3.0 | KiCad action plugins | Via fence generator (pyclipper offsets), plus links to via stitching and teardrop scripts | [README](https://github.com/easyw/RF-tools-KiCAD) [P] |
| rjwalters/kicad-tools | not checked | Python | Protocol-aware pair rules emitting KiCad-native `diff_pair_gap`, uncoupled, `skew`, `via_count` | [issue #6443](https://github.com/rjwalters/kicad-tools/issues/6443) [S] |

**jasonarnoldarnie `return_path` details.**
- Reference plane per layer is the nearest copper layer *by dielectric thickness* that carries zone fill; the stackup is parsed from the `.kicad_pcb`. Zones are refilled in memory.
- Tracks are sampled every 0.1 mm against a 0.05 mm raster of fills labelled by net.
- Flag kinds: VOID (detour = A* shortest path through plane copper between the gap's entry and exit points minus the bridged length; FAIL above 1.0 mm); ISLAND (no connection across the gap on that layer); SPLIT (the plane under the trace changes net); TERMINAL; VIA (same-net planes: nearest stitching via spanning both planes, FAIL above 2.0 mm; different nets: best-loop capacitor, FAIL above 5.0 mm); EDGE (plane edge within w/2 + k·h, k = 3).
- Loop area = length × h + plan-view detour area (shoelace) + via-to-return-via distance × plane spacing.
- Net-name class severity caps; HTML visualisation of predicted return current with a 1/(1+(x/h)²) glow out to ±3h.
- Stated limitations: plane copper only; no spreading model.

**kicad-happy EMC skill details.**
- Ground-plane voids; layer transitions without a nearby GND via; trace near the edge (< h on outer layers); via stitching (uniform-density estimate √(area/count) vs λ/20 at 3× the highest crystal frequency).
- Crosstalk "3H" on outer layers (grid-cell proximity, ≥5 mm coupled length).
- Diff-pair skew and resulting common mode; ESD path; connector filtering and ground-pin ratio; cavity resonances; switching harmonics; PDN; risk score.

**EMI Guardian details.**
- Reference-plane gaps and ground-return detours.
- Return-via gaps (radius 2 mm).
- Parallel coupling: same layer, angle ≤5°, overlap ≥5 mm, spacing ≤0.5 mm, uniform-grid spatial hash. Crosstalk proxy = (h/s)² × overlap / critical length.
- Edge proximity (1 mm); diff-pair mismatch (1 mm); acute corners (<75°); dangling stubs (≥0.8 mm).
- Electrically long nets by longest route diameter (critical fraction 1/6).
- GND-pour appendage antennas (resonance target ≤1500 MHz); stitching planner.
- Dry-run by default; no persistent DRC markers.

**emcvisual rule details.**
- `return-gap`: gap from 0.2 mm; report when the detour is ≥2 mm.
- `ref-change` (different-net planes) and `no-stitching` (same net, no via within 3 mm).
- `edge-trace`: <3h (≥1 mm) over ≥3 mm.
- `cable-cm`: L_p = (4/π²)·µ0·l·h/(d1+d2), V = ωL_p·I, E = 0.365·V; cites the Clemson expert system and Hockanson/Hubing 1996.
- `io-coupling`: M = µ0/(4π)·ln(1+4h²/s²); E = 40·V/Z_ant, Z_ant = 80(N+1) Ω.
- `long-line`: quarter-wave in band with no ≥10 Ω series R within 15 mm.
- Filters >10 mm from the pin; ESD diode nearer the IC than the connector; crystal near an edge or connector; hot loop ≥30–40 mm².

### Inferences

#### Algorithm specifications for the non-native checks (synthesis; each cites its physics)

**A. Reference-layer map (prerequisite for B–E).**
1. Read the stackup: IPC `get_stackup()`, or parse `(stackup …)` in the `.kicad_pcb`.
2. For each signal layer, record both neighbouring copper layers, their dielectric distances h_up and h_down, and whether each is a plane on the relevant region: a zone fill, preferably GND or a declared reference net.
3. The reference is the nearer filled layer, as the return_path checker does. For stripline, keep both, since about 75% of the current returns on the nearer plane per Adamczyk [P].
4. Refill zones before analysis.

Ott's objective 1 (signal layer adjacent to a plane) becomes a stackup lint here.

**B. Return-path continuity and detour.**
1. Fast path: KiCad master `return_path`, a polygon subtract of track copper minus the reference-layer fill union.
2. Full path: per-segment sampling plus a raster or polygon fill labelled by net.
3. For each unreferenced run, compute the geodesic detour through same-net plane copper between entry and exit (A* on a raster, or a visibility graph on polygons).
4. Classify as VOID (detour), ISLAND (no path) or SPLIT (net changes).
5. Before testing, merge antipads and clearances into void polygons, so via-field slots are caught (Ott's slot table).
6. Buffer the trace by 1.5 W (TI) or w/2 + 3h (±3h band) to catch near-void and near-edge runs.
7. Severity scales with net class (t_r) and with detour length relative to h.

**C. Reference-plane-change detection (Ott's order 1–4).**
1. At every via or PTH pad of a classified net, find the layers actually used: track endpoints within the pad radius, plus SMD pads hit.
2. Map each used layer to its reference plane(s) (A).
3. If the set of reference planes is unchanged (a via through the same plane), there is no issue (Ott case 2).
4. If the same net is on different layers (case 3), find the nearest via of that net spanning both plane layers. Report the distance d. Extra loop ≈ d × plane separation. Threshold: TI ≤200 mil, preferably about 1–2 mm.
5. If the nets differ (case 4), find the capacitor minimising the loop pos→padA→padB→pos with pads on the two plane nets. Report it, and warn that it adds 5–10 nH (Ott). Recommend re-layering instead.

**D. Loop-area estimate and differential-mode emission screen.**
1. A_loop = Σ(length × h) + Σ(detour plan-view area) + Σ(d_via × Δz). This is the return_path checker's model.
2. Screen with Ott's E = 2.632×10⁻¹⁴·f²·A·I/r (via kicad-happy) at clock harmonics up to the knee 1/(π·t_r), using I from V/Z0.
3. Use it for *ranking* only. LearnEMC warns radiation is not proportional to loop area for well-designed long lines; the cable common-mode path (F) usually dominates.

**E. Crosstalk coupled-length estimation.** See §6 for the steps: spatial hash, parallel overlap extraction (angle ≤5°), Johnson K = 1/(1+(D/H)²), saturation min(1, 2T/t_r), microstrip FEXT ∝ L/t_r, per-victim aggregation of the two nearest neighbours plus the next two, and stricter budgets for I/O and analog victims (LearnEMC). EMI Guardian's (h/s)² proxy is a cruder variant of the same scaling.

**F. Connector clustering and "high speed between connectors."**
1. Identify cabled connectors (connector footprints with off-board cables). Each one's reference point is the centroid of its ground or shield pins.
2. **Cluster score:** all connector reference points within one edge band (distance to a single outline edge ≤ some fraction of board width), or within one corner quadrant. Report the maximum pairwise distance and angular spread along the outline.
3. **Between test**, for each fast net and each pair of cabled connectors (A, B): run the LearnEMC MREMC approach. Classify the connectors relative to the trace's span (same side versus opposite sides), compute L_return from trace height, length and distances to the board edges, and estimate V_cm (current-driven: 2πf·L_return·I; voltage-driven: h_imbalance·V) and E_max = F_max·0.55·V_cm·factors.
4. Flag if E_max is within 6 dB of the limit, as emcvisual does. Alternatively, flag V_cm > 1 mV (Class B) or > 100 µV (stricter), per LearnEMC.
5. Use this as a placement cost term and as a post-route check.

**G. Via-fence and stitching pitch.**
1. For each pair of ground planes (or plane plus ground pour) that bound signal layers, collect the GND vias and PTH pads spanning both.
2. Clip to the overlap of both fills and compute the largest empty circle: the Voronoi vertex farthest from all vias, inside the region. Its diameter d_max is the largest unstitched span.
3. Require the local cavity's lowest resonance c/(2√εr·d_max) > f_max, using LearnEMC's cavity formula. f_max is the knee of the fastest edge. For aperture-type concerns (edges, fences, compartments), require d_max and edge-gap ≤ λ/20 at f_max (Ott red flag).
4. Prefer distributed stitching over perimeter-only rings (LearnEMC).
5. For an explicit fence along a net (GUARD), measure the maximum gap along the offset polyline. KiCad master's via-stitch GUARD mode (default pitch max(2 mm, 2×via)) can *generate* the fence.

**H. Via stub length.** See §5 for the steps: stackup z-depths; used span from attached tracks; stub = plated barrel beyond the used span, plus pad rings, minus any KiCad 10 backdrill; f_res = c/(4·stub·√εr); flag above min(15 mil, 0.3/Gbps).

**I. Other non-native checks.**
- I/O zone discipline: rule areas plus a "no unrelated trace between connector and device" corridor check.
- TVS, filter and CMC nearer the connector than the IC, with a short ground via (emcvisual / TI SLVA680 logic).
- Floating copper and metal islands: zone fill pieces without pad or via connectivity (HyperLynx "metal island", Ott red flag).
- Clock edge-rate-to-period ratio < 10% (Ott red flag, HyperLynx rule).

#### Encodability matrix
| Rule family | KiCad 9/10 native | KiCad master | External (G/S) |
|---|---|---|---|
| Width / gap per layer for Z0 | `track_width`, `diff_pair_gap` with `(layer …)` | same | S: field solve |
| Intra-pair skew; bus skew | `skew` (`within_diff_pairs`); KiCad 10 time domain | same | n/a |
| Length / delay matching across series parts | partial | `net_chain_length` (bridging) | n/a |
| Uncoupled length; via count; edge clearance; angles | native | native | n/a |
| Return path covered on one reference layer | n/a | `return_path` | G: automatic layer selection, buffers, detours |
| Reference change → via or cap proximity | n/a | n/a | G (C) |
| Loop area | n/a | n/a | G (D) |
| Trace stubs | n/a | `stub_length` (net chains) | G for plain nets |
| Via stubs | backdrill modelling only | n/a | G (H) |
| Crosstalk coupled length | n/a (clearance only) | n/a | G (E) |
| Connector clustering / between connectors | n/a | n/a | G (F) |
| Stitching / fence pitch | n/a | generator only | G (G) |
| Protection and filter topology | n/a | n/a | G (I) |

### Gaps
- KiCad master's `return_path` / net-chain features are unreleased. Their final syntax may change before KiCad 11.
- Whether KiCad master will expose net-chain names in rule conditions (for example `A.NetChain`) was not determined from the code read.
- The open-source checkers' accuracy has not been benchmarked against measurements or full-wave results; emcvisual claims a full-wave comparison, which was not reviewed.

---

## 12. Implications for an LLM-driven KiCad placer/router

### Takeaway
Encode physics, not slogans. One interface and net-class rule table (with t_r, Z, skew budgets, via limits and in-line part placement) should drive two outputs: (1) KiCad-native constraints, including KiCad 10 time-domain profiles and KiCad master `return_path` / `stub_length` where available; and (2) a Python checker suite implementing algorithms A–I above. Build on reading the stackup and zone fills through IPC. Use the LearnEMC source–coupling–antenna framing to rank findings by estimated common-mode voltage, rather than counting rule violations. Hubing: "a board that complies with 90% of the guidelines may be much worse than a board that complies with only one or two."

### Cited Findings
- **Net information.** Rule checkers obtain it from manual entry, net-name substrings, component-database classification or IBIS/simulation data. Naming conventions alone "can not provide detailed information about the nature of the signal." [P] — [LearnEMC rule checkers](https://learnemc.com/commercial-emc-rule-checkers)
- **LearnEMC.** Treat every pin of an internally fast-clocked IC as a potential high-frequency source, because power and low-speed pins can carry clock-harmonic current (near-field scans show more current on DRAM supply pins than on signal pins). [P] — [LearnEMC PCB Layout](https://learnemc.com/pcb-layout)
- **The return_path checker** lets a `return_path_classes.json` override net-name classification, because "names don't always say what a net does." [P] — [return_path README](https://github.com/jasonarnoldarnie/kicad-tools)
- **Rank by consequence.** kicad-happy ranks by risk score with per-rule caps. emcvisual orders findings by their computed share of the far field. [P] — [kicad-happy](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md); [emcvisual](https://github.com/tombueng/emcvisual)
- **Johnson:** promising EMI tools are "more like expert systems than simulators." **Hubing / Clemson:** source/path/antenna combinations are computer-identifiable from layout plus component data. [P] — [Johnson emisim](https://www.sigcon.com/Pubs/edn/emisim.htm); [LearnEMC CM calculator](https://learnemc.com/ext/calculators/mremc/cmode.php)

### Inferences

**A. Net and component classification.**
- Use regex seeds by net name (USB/PCIe/HDMI/MIPI/DDR/QSPI/clock/MDI patterns, `_P/_N`, `+/-`, `_t/_c`), then pin-function and datasheet confirmation by the LLM, then user overrides in the style of `return_path_classes.json`.
- Assign each net a rise time (from IBIS, the part family, or a flagged assumption). This parameterises critical length (t_r/6), skew budget (≈0.1·t_r or spec), stub limit (0.3/Gbps), the knee (0.5/t_r or 1/(π·t_r)), and stitching pitch.
- Treat every pin of a fast IC as potentially noisy for I/O-coupling checks (LearnEMC).

**B. Constraint generation.**
- Per-layer impedance classes come from the stackup; skew and length go in KiCad 10 time-domain profiles.
- Class-to-class clearance comes from Johnson's K budget: D ≥ H·√(1/K − 1), computed per layer.
- Emit `edge_clearance` of ≥2–3h per layer for fast classes, keepout rule areas for the I/O zone, `diff_pair_uncoupled`, and `via_count`.
- On KiCad master, also emit `return_path (layer <ref>) (net GND*)` per net chain and layer, and `stub_length`.
- Tag every emitted rule with `rule_id`, `source_url` and `provenance`.

**C. Checker suite (priority order).** B (return path), C (reference changes), H (via stubs), F (connector between-ness), E (crosstalk incl. I/O), G (stitching), I (protection and filters, islands, edge-rate ratio), D (loop ranking).
- Report findings through an HTML or JSON overlay, because KiCad 10 IPC cannot create persistent custom DRC markers. Selection and zoom via IPC works.

**D. Placer.**
- Staged per §8.
- Cost terms: the MREMC-style "between connectors" V_cm estimate, I/O-zone intrusion, fast-net length and crossings, differential-pair direction alignment (Johnson), and crystal, inductor and switch-node distance to edges and connectors (emcvisual thresholds).

**E. Router.**
- Assign fast nets to layers whose reference is a GND plane.
- Prefer Ott's order 1→4 at layer changes. Auto-insert a GND return via within about 1–2 mm (≤200 mil) whenever the reference set changes between same-net planes, and refuse power↔ground changes unless the user approves a stitching capacitor.
- Route pairs coupled with symmetric breakouts and running-skew compensation. Keep coupled serpentine switchbacks short or uncoupled (Johnson).
- Route into connector pads from the non-stub end (Telian).

**F. Stackup step before placement.** Use the candidate library and scoring in §2.

**G. Knowledge-base schema.** `rule_id, family, statement, numeric{value, unit, basis: mm|ps|W|h|λ|fraction_of_tr}, physics_why, applies_if{interface, t_r<, data_rate>, layer_type, enclosure, emission_class}, severity, check_type{K,K11,G,S}, kicad_dru_template, checker_fn, source_url, source_author, source_type, provenance{P,P-code,S}, confidence, conflicts_with[]`. Include negative (myth) rules from §9.

**H. Licensing note for reuse.** kicad-happy and EMI Guardian (MIT), emcvisual (0BSD-style) and KiCad (GPL-3.0+; kipy is MIT, per its [LICENSE](https://gitlab.com/kicad/code/kicad-python/-/raw/main/LICENSE) [P]) can inform or seed code subject to their licences. jasonarnoldarnie/kicad-tools has no licence, and RolandWa's EMC Auditor is non-commercial proprietary. Use them as algorithm references only.

### Gaps
- No public system was found that closes the loop, generating constraints, routing, and running these physics checks automatically inside KiCad. Every tool reviewed is a post-layout checker or generator.
- The stability of the IPC API across KiCad 10.x and 11 was not verified in this pass.
