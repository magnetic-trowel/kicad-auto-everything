# SI fundamentals: return paths, reference planes, rise time, crosstalk

*Evidence tags:*
- [P]: read in the primary source (an app note, an author's article, or code).
- [S]: snippet or secondary source.
- [V]: unverified vendor or project claim.
- [I]: our inference.

*VR statuses come from `verification_rules.md`, which overrides the catalogs:*
- VERIFIED: the number matches the source.
- +CTX: the number matches, but a condition was dropped.
- CORRECTED: the source says something different.
- CONTESTED: primary sources disagree.
- NOT RETR.: the source could not be retrieved.

**TL;DR**
- High-frequency return current flows in the adjacent plane, directly under the trace: 80% within ±3h for microstrip, 99% for stripline. So every fast net, and each leg of a pair, needs continuous reference copper under its full length.
- Breaks in that copper (gaps, slots made by merged antipads, reference changes) force a detour. The detour causes a reflection, ground bounce and EMI. Rules that follow from this:
  - Use Ott's layer-change order.
  - Place a return via within ≤200 mil, scaled with data rate down to about 1.3 mm at PCIe Gen5.
  - Use stitching capacitors (≤1 µF) only where a split crossing is unavoidable.
- Electrical length is judged against **rise time**, not clock period. At t_r/6, flag the net for SI review; at t_r/2, it must be terminated (the threshold is CONTESTED). Slow the edges before adding termination. Keep stubs below min(15 mil, 0.3/Gbps).
- Crosstalk follows K = 1/(1+(D/H)²). Reduce h first, then set spacing from a crosstalk budget. Guard traces and ground fill are never defaults.
- Express every rule in units of h (taken from the stackup) and per-net t_r. Never use bare slogans such as "3W".

## Key facts

### Where return current flows
| Fact | Value | Source |
|---|---|---|
| Return path location | Above the frequency where ωL dominates, the return runs "directly underneath the signal currents" (the lowest loop inductance). Bogatin's Rule #7: "always use a continuous return path adjacent to every signal path" | [Bogatin/LeCroy](https://www.teledynelecroy.com/oscilloscope/blog/signal-return-paths-signal-and-power-integrity-tutorial/) [P]; [SIJ 20 rules](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers) [P; VERIFIED] |
| Plane type | The return uses the plane directly beneath, whether power or ground. With 1 oz copper above 30 MHz the currents are surface currents, so a plane acts as two conductors | [Ott P6](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html) [P] |
| Adjacent plane takes all of it | An L1 signal returns 100% in an adjacent L2 ground, even with 20 planes. Two or three signal layers sharing one plane leave "fields intermingling … where EMI comes from" | [Hartley/Altium](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley) [P; VERIFIED as a paraphrase] |
| Lateral spread | Microstrip: 50% within ±1h, 80% within ±3h, 97% within ±10h. Stripline: 99% within ±3h, about 75% on the nearer plane. Because w ≈ 2h at 50 Ω, TI's "1.5 W from voids" ≈ 3h, which is the same physics [I] | [Adamczyk](https://incompliancemag.com/pcb-return-current-distribution-in-a-microstrip-line/) [P] |
| Return pins | The signals closest to a good return suffer the least ground bounce, so spread return pins among signal pins | [Johnson](https://www.sigcon.com/Pubs/edn/SpreadYourReturns.htm) [P] |
| 3-D scaling | A 0.063" via at 500 ps behaves like a Euro-connector at 5 ns. It therefore needs a 10:1 signal:ground via ratio, i.e. a "carpet of vias" | [Johnson](https://www.sigcon.com/Pubs/edn/ConnectLayers.htm) [P] |
| Differential pairs | They are not self-returning; each leg returns under itself. In a 2.5 Gb/s XAUI case, a pair on a power plane with its SMA grounds on ground gave a "horrible" eye. The fix was a ground island under the connectors (6 mil gap, pair about 12 mil apart at the crossing) | [Johnson](https://www.sigcon.com/Pubs/edn/ReturnCurrentMatters.htm) [P] |
| Common mode | A via that changes reference planes "greatly magnif[ies]" common-mode current | [Archambeault](https://www.sigcon.com/Pubs/edn/ReducingEmissions.htm) [P] |
| Loop area | The return follows least inductance at MHz and least resistance at kHz. "Radiation is NOT proportional to loop area": well-designed long lines need not radiate | [LearnEMC](https://learnemc.com/the-most-important-emc-design-guidelines) [P] |

### Discontinuities: splits, slots, voids, reference changes
- **Bogatin's "trifecta" for a split:**
  1. a reflection;
  2. ground bounce and shared-path crosstalk;
  3. EMI from the voltage across the plane.
  
  The only benefit of a split is low-frequency resistive isolation. That requires the gap to run parallel to the signals and never be crossed [P].
- **Ott's slot measurements.** Plane voltage across 1" under a 10 MHz trace with 3 ns edges ([Slots](https://hott.shielddigitaldesign.com/techtips/tips-slots.html) [P]):

  | Slot under trace | Plane voltage |
  |---|---|
  | none | 15 mV |
  | ¼" | 20 mV |
  | ½" | 26 mV |
  | 1" | 49 mV |
  | 1.5" | 75 mV |
  | 15 holes of 0.052" over 1" | 15 mV |

  So merged antipads behave like a slot, while separate holes do not. Ott also suggests ordering one board etched but not laminated, so the buried planes can be inspected.
- **Ott's layer-change order**, best to worst ([P](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html)):
  1. Stay on one layer.
  2. Change between two layers adjacent to the same plane. A via through that plane is *no* discontinuity, because the antipad wall joins the plane's two surfaces.
  3. Change between same-net planes, with a GND via "immediately adjacent".
  4. Change between different-net planes. The return then goes through the nearest decap, which adds 5–10 nH. Interplane capacitance only helps "considerably above 500 MHz".
- **Return-via distance at a reference change:**
  - TI: "symmetrically within 200 mils (center-to-center, closer is better)" ([SPRAAR7J p.8](https://www.ti.com/lit/pdf/spraar7) [P; VERIFIED]). The 40 mil and 1 mm figures are [S] only.
  - TI Gen5: within 50 mil, "as many as possible" ([SNLA426](https://www.ti.com/lit/pdf/snla426) [P]).
  - EMA: ≥2 vias within 100–200 mil, placed on both sides of a pair ([EMA](https://www.ema-eda.com/wp-content/uploads/2025/10/PCIe-Design-Guide-Part-1.pdf) [P]).
  - Renesas: adjacent, but not so close that it disturbs the impedance ([Renesas](https://www.renesas.com/en/document/apn/pcie-buffer-mux-layout-recommendations?r=1565126) [P]).
  - Qualcomm: a C-shaped GND-via ring at clock and RF transitions ([CXO](https://docs.qualcomm.com/doc/80-PV086-5P/topic/CXO-and-SLEEP_CLK-routing.html) [P]).
  - Rate scaling [I]: about 5 mm at ≤5 Gb/s, about 2.5 mm at Gen3/4, about 1.3 mm at Gen5.
- **Stitching capacitors.**
  - **CORRECTED:** "1–10 nF within 50 mil at GND↔PWR changes" has no primary source ([AtlasPCB](https://www.atlaspcb.com/blog/pcb-via-transition-return-current-path-signal-integrity/) [S]).
  - TI's primary value applies to *split crossings*: "1 µF or lower … as close as possible to the plane crossing" ([SPRAAR7J p.7](https://www.ti.com/lit/pdf/spraar7)).
  - For a slot crossing, Ott gives 0.001–0.01 µF within 0.1" on each side of the trace. If both power and ground are split, no trace may cross [P].
  - u-blox gives no value ([NORA-B2 p.19](https://content.u-blox.com/sites/default/files/documents/NORA-B2-u-connectXpress_SIM_UBXDOC-465451970-3906.pdf)).
  - TI SLLU149E: put bypass caps next to the vias.
- **TI SPRAAR7J rules:**
  - Keep traces ≥1.5 W from voids [VERIFIED+CTX: this applies to HS differential pairs and is waived at intentionally voided SMD pads].
  - "TI does not recommend high-speed signal references to power planes" [VERIFIED].
  - Never overlap planes that do not reference each other.
- **Unavoidable split:** use one bridge and route every crossing over it ([Ott](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html); [TI SLYT512](https://www.ti.com/lit/an/slyt512/slyt512.pdf) [VERIFIED]).
- **HyperLynx DRC "interrupted return path"** ([whitepaper](https://schematicsforfree.com/files/Manufacturing%20and%20Design/PC%20Board%20Design%20and%20Fabrication/PCB%20Design,%20Layout%20&%20Routing/USING%20HYPERLYNX%20DRC%20TO%20FIND%20EMI%20ISSUES.pdf) [P]):
  - It covers three cases: a gap crossing; running near a plane edge (the board edge or a large void); and a reference change.
  - A P↔G change needs a capacitor. A G↔G change needs a via.
- **LearnEMC** ([PCB Layout](https://learnemc.com/pcb-layout) [P]):
  - A gap crossing is a *conducted* common-mode source that drives the cables on either side.
  - On boards with solid planes, use no ground traces or fill on other layers; connect ground by a via straight to the plane.
  - Never filter by routing over a gap, or by putting a ferrite on ground.
- **Clemson:** longer gaps give more common-mode current [S; NOT RETR.].

### Rise time, critical length, termination, stubs
- **Critical length (CONTESTED):**
  - Johnson: a line needs termination at somewhere between 1/10 and 1/3 of t_r. At ½ t_r expect "severe overshoot and ringing"; he simulates anything over 1/6 ([Johnson](https://www.sigcon.com/Pubs/news/3_14.htm) [P]).
  - LearnEMC and ADI MT-097: terminate at ≥t_r/2. MT-097's conservative variant is 2 in per ns; 2" of microstrip at Er 4 is about 270 ps ([MT-097](https://www.analog.com/media/en/training-seminars/tutorials/MT-097.pdf) [P]).
- **Slow the edge first** ([LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines) [P]):
  - Use a matched termination only as a last resort.
  - Default to a series R on capacitive loads, and remove it where it is clearly unnecessary. Use resistors, not ferrites.
  - Aim for a transition time of about 20% of the UI. "100 MHz … should never fail at 2 GHz."
  - These are not valid criteria: "terminate beyond λ/4", "series R above 1 V/ns", "Z ≥ Z0/4".
- **Archambeault:** on a 12" trace at 133 MHz, moving the source termination from 10 to 39 Ω cut harmonic current by 10–20 dB. Choose the termination for **minimum current**, not just an acceptable voltage [P].
- **Hartley:** problems track rise time, not clock frequency.
- **Stub limits:**
  - Ott: L[in] ≤ t_r[ns] ([Rules of thumb](https://hott.shielddigitaldesign.com/techtips/rulesofthumb.html) [P]).
  - Bogatin, via Telian: the ¼-wave stub length is 3/Gbps inches; with a 10× margin, keep stubs **<0.3/Gbps** ([Telian SIJ](https://www.signalintegrityjournal.com/articles/2962-fixing-the-problem-of-stubs) [P; VERIFIED]).
    - A 12" channel at 12 Gb/s with a 0.250" stub passes <2% at 6 GHz; with a 0.025" stub there is no visible effect.
    - At 30 Gb/s the limit is about 10 mil. A non-backdrilled via stub is 11 mil (4 + 3 + 4). Count the middle pad ring even on backdrilled vias. "50 mils is too long for even an 8 Gbps stub."
  - Quarter-wave frequency: f ≈ 1.5/L[in] GHz [S; EDN NOT RETR., but arithmetically consistent].
  - TI: <15 mil, otherwise backdrill [VERIFIED].
  - Gen5 maximum: about 54 mil (Megtron 6) or 51 mil (FR4).
  - EMA: a 20 mil stub resonates at 8–16 GHz.
  - LPDDR4: ≤20 mil (CA) and ≤40 mil (data).
- **Alternatives to backdrill:** near-outer layers (L1 to L15 of 16), sequential lamination, or blind/buried vias. Decide the stub strategy before the stackup (Telian).
- **Pads as stubs:**
  - Enter a connector pad from the end opposite the solder leg; otherwise there is a pad stub of about 50 mil. Use SMT connectors at 25+ Gb/s (Telian).
  - TI: enter through-hole receptacles on the bottom layer, and SMT receptacles on top with no vias [VERIFIED].
- **SerDes:** zero test points and zero stubs. VR reclassifies this as a P0 "zero", not "minimise".

### Crosstalk
- **Johnson** ([Noise Isolation](https://www.sigcon.com/Pubs/news/2_13.htm) [P]):
  - Worst-case NEXT is **K = 1/(1+(D/H)²)**, where D is the centre-to-centre separation.
  - When 2·T_coupled < t_r, K scales down in proportion. D/H = 100 gives 80 dB.
  - Sum the two nearest aggressors, plus a little from the next two.
  - Differential pairs barely cancel aggressor coupling ([P](https://www.sigcon.com/Pubs/news/3_20.htm)).
  - For extreme isolation, place the trace between same-voltage planes with a via row at about ¼" pitch.
- **Ott:** <2% at s = 4h (microstrip) or s = 2h (stripline); crosstalk ∝ h² at fixed spacing ([Ott P2](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-2.html) [P; VERIFIED]).
- **Bogatin #20/#21:** 2W spacing gives about 2.5% NEXT; FEXT ≈ 0.5%·Len[in]/RT[ns] [S; NOT RETR.].
  - Cross-check [I]: with w ≈ 2h, a 2W gap means D = 6h, and K ≈ 2.7%. The three rules agree, so encode Johnson's closed form.
- **Johnson, broadside pairs:** in a 20.5 mil cavity, moving traces from 6 to 4 mil above the plane (7→5 mil wide) cut crosstalk from 220 to 143 mV at 13 mil pitch and from 38 to 25 mV at 19 mil pitch, about 35% less [P].
- **Guard traces** (CORRECTED; see [myths-and-contested.md](myths-and-contested.md)): stripline only, end-shorted and length-matched; never in microstrip.
- **Ground fill** on multilayer boards does nothing and modulates Z0 ([Johnson](https://www.sigcon.com/Pubs/edn/GroundFill.htm) [P]).
- **I/O coupling:** fast nets near I/O nets drive cable common mode (LearnEMC; this is also a HyperLynx rule).
- **Adjacent signal layers:**
  - TI: route them "at a 90° offset" ([SPRAAR7J p.14](https://www.ti.com/lit/pdf/spraar7) [P; VR FOUND]); HD3SS3220 says the same.
  - Ott pairs H and V layers on a shared plane.
  - Cross analog and digital at right angles [S].

## Recommendations for our system
- **Build the reference-layer map first**, from the stackup plus zone fills: [checkers-si-emi.md](checkers-si-emi.md) checker A. Then express edge, void, crosstalk and stitching rules in units of h.
- **Give every net a t_r:** from IBIS, from the part family, or as an LLM estimate flagged as an assumption. t_r parameterises:
  - the critical-length flags (t_r/6, t_r/2);
  - stub limits;
  - skew budgets ([diff-pairs.md](diff-pairs.md));
  - the knee frequency, 1/(πt_r) or 0.5/t_r;
  - the stitching pitch.
- **Router policy:**
  - Follow Ott's order 1→4.
  - Auto-insert a GND via within about 1–2 mm (≤200 mil) when the reference changes between same-net planes.
  - Refuse P↔G reference changes unless the user approves a stitching capacitor.
  - Treat a via that passes through the same plane as fine.
- **Never auto-insert terminations.** Recommend slew control or a series R, and flag the net for SI review.
- **Spacing:** D ≥ H·√(1/K − 1) per layer, with a stricter K for I/O and analog victims. No guard traces or fill by default.

## Conflicts and open questions
- **Termination threshold:** t_r/2 (LearnEMC, ADI) vs 1/6 (Johnson). Resolve as "review" vs "must terminate".
- Bogatin's NEXT and FEXT rules of thumb could not be retrieved; Johnson's formula stands in.
- **Open:**
  - No primary source quantifies how much removing unused pads shortens a stub.
  - Parallel-termination placement was not researched.
  - No primary source gives emissions in dB as a function of slot length.

## Sources
- Research notes:
  - [rules_highspeed_emi.md § 1, 5, 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)
  - [verification_rules.md § 1A, 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
  - [interface_rule_packs.md § 9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
- Primary sources:
  - Ott tech tips (https://hott.shielddigitaldesign.com/techtips/index.html)
  - Johnson (https://www.sigcon.com/Pubs/edn/)
  - TI SPRAAR7J (https://www.ti.com/lit/pdf/spraar7)
  - LearnEMC (https://learnemc.com/pcb-layout)

See also:
- [stackup.md](stackup.md)
- [diff-pairs.md](diff-pairs.md)
- [emc-placement.md](emc-placement.md)
- [checkers-si-emi.md](checkers-si-emi.md)
- [myths-and-contested.md](myths-and-contested.md)
