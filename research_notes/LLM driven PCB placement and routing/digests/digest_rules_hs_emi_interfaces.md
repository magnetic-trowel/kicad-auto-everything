# Digest: High-Speed/SI, Differential Pairs, EMI/EMC, Stackup and Interface Rule Packs

**Inputs.** `rules_highspeed_emi.md` **[HS]** and `interface_rule_packs.md` **[IF]**, both read in full. From `verification_rules.md` **[VR]**: §1A in full, plus the §1B crystal/edge rows, the §2 HS/EMC/RF/DFM additions and the §3 hard/soft classification. **Where VR conflicts with HS or IF, the VR value is used here and the conflict is marked.**

**Tags.** [P] = primary source read in full. [P-code] = read from source code. [S] = search snippet only. [D] = derived by the note author. VR status tags:
- VERIFIED;
- +CTX (the number is right but a condition was dropped);
- CORRECTED;
- CONTESTED;
- NOT FOUND;
- NOT RETR. (not retrievable).

**Units.** 1 mil = 0.0254 mm. W = trace width. h or H = height above the reference plane. t_r = rise time. UI = unit interval.

---

## 0. Bottom line

1. **One physical model.** Ott, Hubing/LearnEMC, Bogatin, Johnson, Hartley and Archambeault agree on it:
   - The energy is in the fields in the dielectric.
   - High-frequency return current flows in the adjacent plane, directly under the trace.
   - Radiated EMI comes mainly from **common-mode voltage between two "antenna parts"** (cables, chassis) and from **imbalance or skew**.
   - So the system should encode the physics, not the slogans. In Hubing's words: "a board that complies with 90% of the guidelines may be much worse than a board that complies with only one or two" ([LearnEMC](https://learnemc.com/why-you-should-be-cautious-about-using-emc-design-guidelines) [P]).
2. **Vendor values for one interface differ 5–25×.** USB3 intra-pair skew ranges from 2 mil to 0.7 mm; DDR4 DQ↔DQS from 2 ps to 25 ps; Ethernet PHY↔magnetics is ≥25 mm per one vendor and <25 mm per another. A **vendor profile is mandatory**. When the vendor is unknown, use the tightest primary value and record an `info` finding.
3. **VR found that named vendor app-note numbers mostly hold.** The usual defect was a **dropped applicability condition**: device family, data rate, enclosure versus PCB, or a single measured part. Rules therefore need `applies_if`, `source_scope`, `statement_strength` and `contested_by` fields.
4. **Blog-only millimetre thresholds were never confirmed by a primary source.** These are TVS ≤5–10 mm, crystal ≤5 mm, CIN ≤0.5–1 mm, RF↔SMPS 20 mm and stitching 3–5 mm. They become **ranked or comparative objectives**, not DRC errors.
5. **KiCad checks part of this natively.**
   - KiCad 10 checks most skew, length and delay rules: ps units, `fromTo()` paths, per-layer and via delay, and backdrills.
   - KiCad master (unreleased) adds `return_path`, `stub_length`, net chains and a via-stitch generator.
   - Everything else needs custom geometric checkers (algorithms A–I, §8) or simulation budgets.
6. **No public system closes the loop.** None generates constraints, routes, and then runs these physics checks inside KiCad. Every tool reviewed is a post-layout checker or a generator ([HS] §12).

---

## 1. Physics fundamentals: return paths, loop area, rise time, crosstalk, radiation

### 1.1 Where return current flows
- **Bogatin.** Above the frequency where ωL dominates, "the return currents are always flowing directly underneath the signal currents", because that path has the lowest loop inductance ([Teledyne LeCroy](https://www.teledynelecroy.com/oscilloscope/blog/signal-return-paths-signal-and-power-integrity-tutorial/) [P]). Bogatin's Rule #7: "always use a continuous return path adjacent to every signal path" ([SIJ](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers) [P; VERIFIED]).
- **Ott.**
  - The return flows in the plane directly underneath, "irrespective of whether this is a power or ground plane".
  - Above 30 MHz, 1 oz copper carries surface currents only, so a plane is "two conductors" (its top and bottom surfaces).
  - Source: [Ott Part 6](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html) [P].
- **Hartley.**
  - With L1 signal over L2 ground, 100% of the return is in L2, even if the board has 20 ground planes.
  - Two or three signal layers referencing one plane leave "all fields intermingling … one of the places where EMI comes from".
  - Sources: [Altium podcast](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley) [P; VERIFIED, as a paraphrase]; [EEJournal](https://www.eejournal.com/article/matters-of-integrity/) [P].
- **Return-current spread (Adamczyk).**
  - Microstrip: 50% within ±1h, 80% within ±3h, 97% within ±10h.
  - Symmetric stripline: 99% within ±3h; about 75% flows on the nearer plane.
  - Sources: [In Compliance, microstrip](https://incompliancemag.com/pcb-return-current-distribution-in-a-microstrip-line/); [In Compliance, stripline](https://incompliancemag.com/pcb-return-current-distribution-in-the-stripline-configurations/) [P].
  - This gives physical grounding for the edge and void rules. Since w ≈ 2h for 50 Ω FR-4, TI's "1.5 W from a void" is about 3h, so the two rules are the same physics ([HS] inference).
- **Johnson.**
  - The magnetic field lives between conductors. "Signals closest to a good return suffer the least ground bounce", so spread return pins among signal pins ([Spread Your Returns](https://www.sigcon.com/Pubs/edn/SpreadYourReturns.htm) [P]).
  - **3-D scaling:** a Euro-connector at 5 ns needs a 10:1 signal-to-ground pin ratio, so a 0.063" via at 500 ps needs the same 10:1 via ratio. Hence a "carpet of vias" ([Connecting Layers](https://www.sigcon.com/Pubs/edn/ConnectLayers.htm) [P]).
- **Differential pairs are not self-returning.** Each leg returns "almost as if they were two independently routed, single-ended signals".
  - In Johnson's XAUI case at 2.5 Gb/s, the pair referenced a power plane while the SMA grounds tied to ground, and the eye was "horrible".
  - The fix was a ground island carved under the connectors, with a 6 mil gap and the pair about 12 mil apart where it crosses ([Return Current Matters](https://www.sigcon.com/Pubs/edn/ReturnCurrentMatters.htm) [P]).
- **Archambeault.** A via that changes reference planes "tends to greatly magnify" the stray common-mode current ([Reducing Emissions](https://www.sigcon.com/Pubs/edn/ReducingEmissions.htm) [P]).
- **LearnEMC.**
  - Return current takes the least inductance at MHz and the least resistance at kHz.
  - "Radiation is NOT proportional to loop area": long lines that are properly designed need not radiate.
  - Source: [Most Important Guidelines](https://learnemc.com/the-most-important-emc-design-guidelines) [P].

### 1.2 Discontinuities: splits, slots, voids, reference changes
- **Bogatin's split "trifecta":** a reflection, ground bounce plus shared-path crosstalk, and EMI from the voltage across the plane. The only benefit of a split is low-frequency resistive isolation, and only if the gap runs parallel to the signals and is never crossed ([P](https://www.teledynelecroy.com/oscilloscope/blog/signal-return-paths-signal-and-power-integrity-tutorial/)).
- **Ott's slot measurements.** 10 MHz clock with a 3 ns edge; plane voltage measured across 1" under the trace ([Slots](https://hott.shielddigitaldesign.com/techtips/tips-slots.html) [P]):

  | Slot under the trace | Plane voltage |
  |---|---|
  | none | 15 mV |
  | ¼" | 20 mV |
  | ½" | 26 mV |
  | 1" | 49 mV |
  | 1.5" | 75 mV |
  | row of 15 holes of 0.052" over 1" | 15 mV |

  So a slot matters, and separate holes do not. The checker must therefore merge antipads into void polygons and measure the void length perpendicular to the trace. Ott also suggests etching one set of boards without laminating them, to inspect the buried planes.
- **Ott's layer-change order** (best to worst) ([P](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html)):
  1. Stay on one layer.
  2. Change between two layers adjacent to the same plane. A via passing through the plane has **no** discontinuity, because the antipad wall joins the two surfaces.
  3. Change between same-net planes, with a ground via "immediately adjacent" to the signal via.
  4. Change between different-net planes. The return then goes through the nearest decoupling cap, which adds 5–10 nH. Interplane capacitance only helps "considerably above 500 MHz".
- **Return-via distance:**
  - TI places stitching vias "symmetrically within 200 mils (center-to-center, closer is better)" when the same GND reference cannot be kept ([SPRAAR7J p.8](https://www.ti.com/lit/pdf/spraar7) [P; VERIFIED]). The 40 mil and 1 mm figures stay secondary [S].
  - Data-rate-scaled values:
    - TI Gen5: within 50 mil, "as many as possible" around the antipad ([SNLA426](https://www.ti.com/lit/pdf/snla426) [P]).
    - EMA: ≥2 vias within 100–200 mil, on both sides of a pair ([EMA](https://www.ema-eda.com/wp-content/uploads/2025/10/PCIe-Design-Guide-Part-1.pdf) [P]).
    - Renesas: next to the signal via, but not so close that impedance changes ([R31AN0080EU0102](https://www.renesas.com/en/document/apn/pcie-buffer-mux-layout-recommendations?r=1565126) [P]).
    - Qualcomm: a C-shaped ring of GND vias at every clock and RF transition ([CXO routing](https://docs.qualcomm.com/doc/80-PV086-5P/topic/CXO-and-SLEEP_CLK-routing.html) [P]).
  - Parameterise the distance by rate [IF, D]: about 5 mm up to 5 Gb/s, about 2.5 mm at Gen3/4, about 1.3 mm at Gen5.
- **Stitching capacitors.**
  - **VR CORRECTED** the catalog's "1–10 nF within 50 mil" at GND↔PWR changes. That figure has no primary source (only [AtlasPCB](https://www.atlaspcb.com/blog/pcb-via-transition-return-current-path-signal-integrity/) and UGPCB [S]).
  - The primary TI value applies to **split crossings**: "1 µF or lower … as close as possible to the plane crossing" ([SPRAAR7J p.7](https://www.ti.com/lit/pdf/spraar7)).
  - For slot crossings, Ott gives 0.001–0.01 µF within 0.1" on each side of the trace. If both power and ground are split, no trace may cross at all [P].
  - u-blox says only "some capacitors … and an adequate number of GND vias" ([NORA-B2 p.19](https://content.u-blox.com/sites/default/files/documents/NORA-B2-u-connectXpress_SIM_UBXDOC-465451970-3906.pdf) [P]).
  - TI SLLU149E: put bypass caps next to the vias if the reference must change ([P](https://www.ti.com/lit/pdf/sllu149)).
- **Other TI SPRAAR7J rules:**
  - Keep ≥1.5 W from voids. [VERIFIED+CTX: this applies to high-speed differential pairs and is waived at intentionally voided SMD pads.]
  - Prefer a GND reference. "TI does not recommend high-speed signal references to power planes" [VERIFIED].
  - Do not overlap planes that do not reference each other.
- **One bridge per split.** If a split is unavoidable, join the planes at one bridge and route every crossing over it ([Ott](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html); [TI SLYT512](https://www.ti.com/lit/an/slyt512/slyt512.pdf) [P; VERIFIED]).
- **HyperLynx DRC's "interrupted return path"** covers three cases: a gap crossing, proximity to a plane edge (the board edge or a large void), and a reference change. Power↔ground changes need a capacitor; ground↔ground changes need a via ([whitepaper](https://schematicsforfree.com/files/Manufacturing%20and%20Design/PC%20Board%20Design%20and%20Fabrication/PCB%20Design,%20Layout%20&%20Routing/USING%20HYPERLYNX%20DRC%20TO%20FIND%20EMI%20ISSUES.pdf) [P]).
- **LearnEMC.**
  - A gap crossing is a *conducted* common-mode source that drives the cables on each side of the gap.
  - On boards with solid planes, use no ground traces or fill on other layers; connect ground "a via connecting directly to the plane".
  - Never filter by routing over a gap or by putting a ferrite on ground.
  - Source: [PCB Layout](https://learnemc.com/pcb-layout) [P].
- **Clemson EMCS97-159:** a longer gap means more common-mode current [S; NOT RETR.].

### 1.3 Radiation mechanisms and thresholds
- **Antenna model (LearnEMC).** An unintentional antenna needs two parts, neither electrically small, with a voltage between them.
  - Below about 100 MHz, only cables and the chassis qualify.
  - Above 100 MHz: tall parts, heatsinks, seams and sparse planes are good antennas. ICs, traces and densely populated planes are poor ones.
  - **About 1 mV between antenna parts can fail Class B**, and requirements stricter than CISPR 32 B may need **100 µV**.
  - Source: [PCB Layout](https://learnemc.com/pcb-layout) [P; VERIFIED].
- **Magnetic coupling between connectors.** Return flux wraps the plane. "Tens of milliamps at tens of megahertz will effectively induce millivolts", and the effect grows with trace width and height. Stripline produces none. The fix is all connectors on one edge, or a chassis bonded at both connectors [P].
- **MREMC common-mode algorithm**, from Hubing, Su and Zhu's calculator JavaScript ([CMode_algr.js](https://learnemc.com/ext/calculators/mremc/calculator/CMode_algr.js) [P-code]):
  - L_return = (µ0/π)·t·l_t / w_e / √(1 − 4(1 − 2t/w_e)·offset²/w_e²), where w_e = d1 + d2 (distances to the two board edges) and offset = |d1 − d2|/2.
  - L_trace = √(µ0ε0)·l_t·Z0, and imbalance h = L_ret/(L_ret + L_trace).
  - V_cm = h·V_dm (voltage-driven) or 2πf·L_ret·I_dm (current-driven, with I_dm = V/R_L or V·2πf·C_L).
  - E_max = F_max·0.55·V_cm·boardfactor·cablefactor.
    - boardfactor = sin(2πL_eff/λ) when λ ≥ 4L_eff, else 1.
    - cablefactor = sin(2π·1 m/λ) when λ ≥ 4 m, else 1.
    - F_max = 2/sin(√(c/(f·L_cable))) above the cable's half-wave resonance.
  - Assumptions: no shield, cable ≫ board, about 1 m above ground.
- **emcvisual's simpler variants** ([RULES.md](https://github.com/tombueng/emcvisual/blob/main/docs/RULES.md) [P-code]):
  - Cable common mode: L_p = (4/π²)µ0·l·h/(d1 + d2), V = ωL_p·I, E = 0.365·V (Hockanson/Hubing 1996).
  - I/O coupling: M = µ0/(4π)·ln(1 + 4h²/s²), E = 40·V/Z_ant, with Z_ant = 80(N+1) Ω.
- **Ott's formulas**, via kicad-happy (secondary to Ott's book; [MIT repo](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md) [P-code]):
  - Differential-mode loop: E = 2.632×10⁻¹⁴·f²·A·I/r.
  - Common-mode cable: E = 1.257×10⁻⁶·f·L·I_CM/r.
  - Doubling the area adds 6 dB; doubling the frequency adds 12 dB.
- **Cable common-mode current limits.**
  - Ott: <5 µA for Class B and <15 µA for Class A, for cables ≥1 m (0.5 m scales to 10 µA). Measure with a clamp probe (F-33-1, 2–250 MHz) and iterate over every cable ([Ott CM](https://hott.shielddigitaldesign.com/techtips/tips-cm.html) [P]).
  - Hartley: 8–10 µA fails Class B [P].
- **FCC 15.109 radiated limits** ([CFR](https://www.law.cornell.edu/cfr/text/47/15.109) [P]):
  - Class B at 3 m: 100 / 150 / 200 / 500 µV/m for 30–88 / 88–216 / 216–960 / >960 MHz.
  - Class A at 10 m: 90 / 150 / 210 / 300 µV/m.
- **Consistency checks** ([HS], D):
  - Ott's common-mode formula at 100 MHz (1 m cable, 3 m distance, 150 µV/m) gives about 3.6 µA, consistent with Ott's 5 µA rule.
  - MREMC with 1 mV gives about 1.1 mV/m (61 dBµV/m), about 20 dB over Class B. That is why 1 mV is a hard line.
- **Cavity resonance:** f_mn = (c/2√εr)·√((m/L)² + (n/W)²). It is independent of plane spacing ([LearnEMC calc](https://learnemc.com/ext/calculators/cavity_resonance/pcb-res.html) [P]).
- **Spread-spectrum clocking (Johnson)** lowers peak readings when the new spectral lines are more than 100 kHz apart. Never use it as the reference for transceivers, PLL CPUs or RF. Johnson prefers planes, small trace-to-plane spacing, slower edges, and differential or low-swing clocks ([clockmod](https://www.sigcon.com/Pubs/edn/clockmod.htm) [P]).

### 1.4 Rise time, critical length, termination, stubs
- **Critical length is CONTESTED [VR].**
  - Johnson: termination is commonly needed from 1/10 to 1/3 of t_r; at ½ t_r there is "severe overshoot and ringing"; he simulates anything over 1/6 ([Line Length](https://www.sigcon.com/Pubs/news/3_14.htm) [P]).
  - LearnEMC: delay > t_r/2 needs a matched termination ([P](https://learnemc.com/other-good-emc-design-guidelines)).
  - ADI MT-097: terminate at ≥t_r/2. Its conservative rule is 2 in per ns, and 2" of microstrip at Er = 4 is about 270 ps ([MT-097](https://www.analog.com/media/en/training-seminars/tutorials/MT-097.pdf) [P]).
  - **Resolution:** t_r/6 flags a net for SI review; t_r/2 means it must be terminated.
- **Slow the edge first (LearnEMC).**
  - Use matched termination only after slowing edges and shortening traces.
  - By default, put a series R on capacitively loaded digital nets and remove it where it is clearly unnecessary. Use resistors, not ferrites.
  - Target a transition time of about 20% of the UI.
  - "A board operating with a clock speed of 100 MHz should never fail … at 2 GHz."
  - LearnEMC rejects these as decision criteria: "terminate beyond λ/4", "series R above 1 V/ns", and "source Z ≥ Z0/4" ([Not-So-Good](https://learnemc.com/not-so-good-emc-design-guidelines); [Worst](https://learnemc.com/some-of-the-worst-emc-design-guidelines) [P]).
- **Archambeault.** On a 12" 133 MHz clock, moving the source termination from 10 Ω toward 39 Ω cut the harmonic current by 10–20 dB. Choose the termination value for **minimum current**, not just an acceptable voltage waveform [P].
- **Stub limits:**
  - Ott: L[in] ≤ t_r[ns] ([Rules of Thumb](https://hott.shielddigitaldesign.com/techtips/rulesofthumb.html) [P]).
  - Bogatin, via Telian: the quarter-wave stub length is 3/Gbps in, so play it 10× safe with **<0.3/Gbps** ([SIJ](https://www.signalintegrityjournal.com/articles/2962-fixing-the-problem-of-stubs) [P; VERIFIED]).
    - Demonstration: a 12" 12 Gb/s channel with a 0.250" stub transmits <2% at 6 GHz; with 0.025" there is no visible change.
    - At 30 Gb/s the limit is about 10 mil. A non-backdrilled stub is 11 mil (4 mil pad ring + 3 mil dielectric + 4 mil pad ring). Count the middle pad ring even on backdrilled vias. "50 mils is too long for even an 8 Gbps stub."
  - Quarter-wave frequency f ≈ 1.5/L[in] GHz [S; EDN #17 NOT RETR., but arithmetically consistent].
  - TI: <15 mil, otherwise backdrill [P; VERIFIED].
  - TI Gen5 quarter-wave maximum: about 54 mil (Megtron 6) or 51 mil (FR4) [P].
  - EMA: a 20 mil stub already resonates at 8–16 GHz [P].
  - LPDDR4 via stubs: ≤20 mil (CA) and ≤40 mil (data) [P].
- **Alternatives to backdrilling:** route on near-outer layers (L1 to L15 of 16), sequential lamination, or blind/buried vias. Decide the stub strategy **before** the stackup (Telian).
- **Connector pads as stubs.**
  - Telian: enter a pad from the end opposite the solder leg, otherwise there is a pad stub of about 50 mil; 25+ Gb/s needs SMT connectors.
  - TI: for a TH receptacle, enter on the bottom layer so the pin is in the path; for SMT, enter on the top layer with no vias [VERIFIED].
- **Test points and stubs on SerDes:** zero test points and zero stubs. VR rates this a P0 "zero", not a "minimise" ([SPRAAR7J p.9, 16](https://www.ti.com/lit/pdf/spraar7)).

### 1.5 Crosstalk
- **Johnson's coupling coefficient:** K = 1/(1 + (D/H)²) is the worst-case NEXT, with D the centre-to-centre separation ([Noise Isolation](https://www.sigcon.com/Pubs/news/2_13.htm) [P]).
  - If twice the coupled delay is less than t_r, K scales down in proportion.
  - D/H = 100 gives 80 dB.
  - Sum the aggressors: the two nearest neighbours plus a little from the next two.
  - Differential pairs do **not** cancel much aggressor coupling ([Differential Crosstalk](https://www.sigcon.com/Pubs/news/3_20.htm) [P]).
  - For extra isolation, run the trace between two same-voltage planes with a via row at about ¼" pitch.
- **Ott:** <2% crosstalk at s = 4h (microstrip) and s = 2h (stripline). Crosstalk ∝ h² at fixed spacing [P; VERIFIED].
- **Bogatin #20 / #21:** 2W gives about 2.5% NEXT; FEXT ≈ 0.5%·Len[in]/RT[ns] [S; **NOT RETR.**].
  - Cross-validation [HS]: w ≈ 2h, so s = 2w gives D = 6h and K ≈ 2.7%. Ott's s = 4h gives the same D. So encode Johnson's closed form.
- **Johnson's stackup data.** Broadside pairs in a 20.5 mil cavity, with 6→4 mil to the plane and 7→5 mil traces: crosstalk fell 220→143 mV at 13 mil pitch and 38→25 mV at 19 mil pitch, about 35% less [P].
- **Guard traces. VR CORRECTED** the attribution and the geometry.
  - The paper is by **Bogatin & Simonovich** ([DesignCon 2013 / SIJ](https://www.signalintegrityjournal.com/ext/resources/article-images-2019/Guard-Traces---Love-Them-or-Leave-Them/4567Guard_Trace_DesignCon-2013-rev14_Final.pdf) [P]). [HS] had attributed a "−60 dB" threshold to Simonovich alone [S].
  - "−50 dB isolation is perfectly adequate and there is never a need for a guard trace" in most high-speed digital work.
  - Never use a guard in microstrip.
  - In stripline, short both ends with the lowest-inductance via and match the guard's length to the coupled region. That gives −70 dB versus −50 dB.
  - λ/10 stitching was *tested*, and they found "no benefit to stitching the guard trace at all" in some cases. Only 3-D simulation quantifies a guard.
  - Johnson and LearnEMC agree: a solid plane is "the biggest, fattest … guard trace", and guards help only on 2-layer analog boards, grounded at both ends ([Guard Traces](https://www.sigcon.com/Pubs/news/15_02.htm) [P]).
- **Ground fill** does nothing on multilayer boards and modulates the impedance of nearby traces; it helps only on 2-layer boards ([Ground Fill](https://www.sigcon.com/Pubs/edn/GroundFill.htm) [P]). Floating fill is an Ott red flag.
- **I/O coupling:** fast nets near I/O nets push common mode out on the cables (LearnEMC [P]; also a HyperLynx DRC rule).
- **Orthogonal adjacent layers.**
  - TI: "Route directly adjacent signal layers at a 90° offset" ([SPRAAR7J p.14](https://www.ti.com/lit/pdf/spraar7) [P; VR FOUND]). HD3SS3220 says the same.
  - Ott: horizontal/vertical layer pairs referencing the same plane [P].
  - Ott: analog and digital should cross only at right angles [S].

### Implications for our system
- Build a **reference-layer map** (stackup plus zone fills) first. Then express every edge, void, crosstalk and stitching rule in units of **h**, not W.
- Give each net a **t_r**: from IBIS, from the part family, or as an LLM estimate flagged as an assumption. The t_r then drives:
  - the critical-length flags (t_r/6 → SI review; t_r/2 → must terminate);
  - the stub limit, min(15 mil, 0.3/Gbps);
  - skew budgets and the knee frequency, 1/(πt_r) or 0.5/t_r;
  - the stitching pitch.
- **Rank EMC findings by estimated V_cm or I_CM** (MREMC; 1 mV / 100 µV; 5 µA), not by violation count.
- Never auto-insert terminations. Recommend slew control or a series R, and flag the net for SI.
- Derive spacing from a crosstalk budget: D ≥ H·√(1/K − 1). Never emit guard traces or fill on multilayer boards by default.

---

## 2. Stackup selection

**Ott's framework** ([Part 1](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-1.html) [P]):
- Four factors: number of layers, number and types of planes, layer order, and spacing.
- Five inputs to the layer count: signal count and cost, frequency, Class A or B, enclosure shielding, and the team's EMC expertise.
- Five objectives:
  1. every signal layer adjacent to a plane;
  2. signals tight to their planes;
  3. power and ground tightly coupled;
  4. high-speed signals buried between planes;
  5. multiple ground planes.
- 8 layers is the minimum that meets all five; more layers are justified only by routing needs, and there is "very little EMC advantage" beyond 8 [VR].
- 4 layers radiate 15 dB less than 2 layers. Go multilayer above 10–15 MHz.
- Planes give too little interplane capacitance below about 500 MHz, so favour signal-to-plane coupling over power-to-ground coupling on 4- and 6-layer boards.
- Keep the stack symmetric to avoid warp.

**Hartley:**
- Never have two signal layers referencing one plane.
- Never stack power planes with no ground nearby.
- Reject thick S/P/G/S on 1.6 mm boards (planes about 1 mm apart, with a P↔G reference change at every L1→L4 via). It is acceptable only if the planes are a few mils, at most about 10 mil, apart.
- S/P/S/S/G/S is "even worse than the four layer".
- He has disowned his older "Board Stack-up to Control EMI" paper ([P](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley)).

**Hubing:** "No guideline for the optimum layer stack-up … applies to more than a small subset." "Two ground planes above 25 MHz" is outdated ([Not-So-Good](https://learnemc.com/not-so-good-emc-design-guidelines) [P; VERIFIED]).

**Candidate stackup library** (Ott [P], annotated with Hartley [P]; VR verified Fig. 3b, 6, 9 and 11):

| L | Stack (top→bottom) | Ott objectives met | Notes |
|---|---|---|---|
| 4 | S/G/P/S; signal–plane <0.010", core >0.040" | 1, 2 | 0.005" gives ≥10 dB less loop radiation. Hartley: avoid on 1.6 mm with fast edges |
| 4 | G / S+P / S+P / G (power as a wide-trace grid; grounds stitched around the periphery) | 1, 2, 4, 5 | Ott: "best … four-layer" [VR FOUND]. Outer grounds get cut up by pads |
| 4 | G/S/S/P | — | Inner signals are shielded; rework is hard |
| 4 | S+P / G / G / S+P | 1, 2, 5 | Rework-friendly |
| 4 | S/S/G/S | 1 (L2 only) | Hartley's "worst": L1 and L2 share one reference |
| 6 | S/S/G/P/S/S | — | Ott: "NOT to use" |
| 6 | LF / G / HF / HF / P / LF | 1, 2, 4 | Most common. Ott: OK with careful decoupling. Hartley: "even worse". **Encode as a warning with rationale, not a rejection** |
| 6 | H1/G/V1/H2/P/V2 (5/5/40/5/5 mil) | 1, 2 | Orthogonal pairs share a plane |
| 6 | G/S/G/P/S/G | all 5 | Only two routing layers |
| 8 | LF/P/G/HF/HF/G/P/LF | all 5 | GND–GND via at each L4↔L5 change |
| 8 | G/H1/G/V1/H2/P/V2/G (10/5/5/20/5/5/10 mil) | all 5 | — |
| 8 | H1/G/V1/G/P/H2/G/V2 (6/6/15/6/15/6/6 mil) | 1, 2, 3, 5 | Tight P/G core; an Ott favourite |
| 8 | Six routing layers | — | "Definitely not recommended"; use 10 layers |
| 10 | LF/G/HS/HS/P/G/HS/HS/G-or-P/LF | all 5 | Clocks on one HS pair, buses on the other |

**Other stackup inputs:**
- **LearnEMC.**
  - If ≥3 power pins share a voltage, distribute it on a plane pair spaced <0.25 mm, with HF decaps on the side nearest that pair.
  - Put power planes on one layer so they never overlap (balanced ±12 V pairs excepted). The gap between them must be ≥ the plane-to-ground spacing; VR adds ≥3 mm ("Maybe") ([Good](https://learnemc.com/other-good-emc-design-guidelines)).
- **TI.**
  - "At least six layers" for these SoCs; adjacent signal layers at 90°.
  - Route HS pairs on top or bottom over GND. "**TI does not recommend stripline**" [P].
  - VR: **CONTESTED** against Ott's objective 4 (bury HS signals). TI's motive is unexplained; it may be via stubs on its SoC reference boards.
- **Ott's impedance rules of thumb (FR-4):**
  - Microstrip Z0 is 60–70 Ω at w/h = 1 and 40–50 Ω at w/h = 2.
  - Stripline ≈ 0.6× microstrip; asymmetric stripline ≈ 0.75×.
  - Delay is 150 ps/in (microstrip) and 180 ps/in (stripline). Dk is 4.0–5.0, typically 4.5. Z0 ∝ 1/√εr.
- **u-blox:** 50 Ω FR-4 microstrip width is "roughly double the thickness of the dielectric" [VR].
- **Fibre weave (TI):** rotate the routing 10–35° to the weave, or zig-zag; prefer tighter weaves (1080/2116 rather than 7628). NXP: route long traces off-axis ([SPRAAR7J p.3–5](https://www.ti.com/lit/pdf/spraar7); [AN10373](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/powerquicc/2284/2/philips_PCIe_pcb_routing_guide.pdf) [P]).
- **HDMI retimers** recommend L1–L2 of 5–10 mil on 4/6-layer boards ([TMDS181](https://www.ti.com/lit/ds/symlink/tmds181.pdf) [P]).
- **Espressif's 4-layer stack:** L2 a complete GND plane with no signals; L3 power plus a few signals [VR].
- **Fab data:**
  - OSH Park 4-layer: FR408HR, L1–L2 prepreg 7.87 mil, core 39 mil.
  - JLCPCB: Dk 4.5 (2-layer), 7628 4.4, 3313 4.1, 2116 4.16; impedance ±10% (±5% on request); backdrill on 4–32 layers, ≥0.8 mm thick ([JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities) [P]).
- **Johnson's EMC alternatives to clock modulation:** solid planes, minimum trace-to-plane spacing, thin packages, slower edges, differential and low-swing clocks.

**Stackup selection algorithm** ([HS] synthesis; no primary source gives a scoring function):
1. Estimate the routing layers from pin density and BGA escape. If ≥6 routing layers are needed, go to 10 layers.
2. Decide whether buried HS layers (objective 4) are needed, from the edge rates, the emission class and the enclosure.
3. Enumerate the library candidates for that layer count.
4. Reject any candidate with a signal layer not adjacent to a plane (an Ott red flag), with two fast signal layers on one plane, or with adjacent power planes and no ground.
5. Score the survivors on objectives met, minus a penalty for forced P↔G reference changes, minus plane-pair separation where ≥3 power pins share a rail.
6. Minimise h subject to a manufacturable width at the target Z0, put the thickness in the core, and keep the stack symmetric.
7. Pair orthogonal layers that reference the same plane.
8. Field-solve width and gap per layer and per target, and emit per-layer net classes.

### Implications for our system
- The **stackup is the step before placement.** It fixes each layer's reference plane, which via spans change the reference, the stub lengths, and the width and gap per layer. Placement density depends on all of these.
- Ship the candidate library and the scorer. Encode Ott-versus-Hartley and TI-versus-Ott disagreements as **warnings with rationale and a selector**: plane separation, edge rate, via-stub strategy.
- Store the fab's stack options (cores and prepregs) as data; HS notes this was not researched. Emit per-layer impedance classes from a field solver.

---

## 3. Differential pairs

**Physics (Johnson [P]):**
- Each leg returns under itself, so §1 applies to each leg.
- **Common mode from skew:** for small Δt, V_cm,peak ≈ Δv·Δt/(2t_r), so "a 20% skew creates a 10% common-mode component", and common mode dominates both radiation and crosstalk ([CMA of Skew](https://www.sigcon.com/Pubs/edn/CMAofSkew.htm)). kicad-happy implements the same relation, V_CM = V_diff·skew/(2T_rise).
- **Coupling buys little EMI.** In theory 0.5 mm spacing gives about 40 dB of cancellation, but drivers rarely balance better than 1:100, so "0.5 mm is close enough to deliver all the EMI benefit" ([Reducing EMI](https://www.sigcon.com/Pubs/edn/ReducingEMI.htm)).
- LearnEMC: an imbalanced pair can radiate like a single-ended trace [P].
- **Corner skew** ([Skewed Layout](https://www.sigcon.com/Pubs/edn/SkewedLayout.htm)):
  - The outer trace gains 2p, 1.65p or 1.57p per square, chamfered or rounded corner (p = pitch). At p = 20 mil that is 5–6.4 ps per corner. **Rounding does not remove skew.**
  - If the driver's skew is unspecified, assume ≥10% of t_r and budget layout skew to match. Examples: 100BASE-TX balanced to 1:1000 gives about 0.1"; a 2.5 Gb/s driver (200 ps edge) gives about 20 ps.
  - Place ICs so a pair **leaves the driver in the same direction it enters the receiver**, so that left and right turns cancel.
- **Serpentines** ([Serpentine](https://www.sigcon.com/Pubs/edn/serpentine.htm)):
  - With 8/8/5 mil geometry, NEXT ≈ 6%.
  - A coupled switchback whose round-trip delay is ≫ ⅓ t_r distorts the signal. One whose delay is ≪ ⅓ t_r advances the arrival, by up to 2× NEXT per switchback (4× for a full serpentine).
  - Maximum useful coupled switchback: about 1" per ns of t_r, about 0.1" at 100 ps.
  - Delay matching must also match the configuration, width, Dk, loading, thresholds and terminations.
- **Differential vias (XFP):** use an oval antipad with ground vias pinning the planes at each end, and no long stubs ([XtkDiffViaGnds](https://www.sigcon.com/Pubs/edn/XtkDiffViaGnds.htm)).

**Numeric rules (corrected where VR differs):**

| Rule | Value | Source / status |
|---|---|---|
| Pair-to-pair | ≥5W (6 mil → 30 mil) | TI SPRAAR7J [P; VERIFIED] |
| Pair to any other signal | **≥30 mil**; to a clock or periodic signal **≥50 mil**; not within 30 mil of another pair after escape | [SPRAAR7J p.9–10](https://www.ti.com/lit/pdf/spraar7) [VR addition: absolute keep-outs the catalog had omitted] |
| NXP pair-to-other | ≥max(20 mil, 4·h); 30 mil if the aggressor has higher voltage or faster edges | [AN10373 p.4](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/powerquicc/2284/2/philips_PCIe_pcb_routing_guide.pdf) [P] |
| Intra-pair skew | USB3/PCIe/SATA/HDMI 5 mil; USB2 50 mil (TI AM57xx tables) | [VERIFIED+CTX: device-family tables]. MIPI CSI uses mode-conversion S-parameters, estimated as UI/50 |
| Skew compensation | Add length "near the location where the mismatch occurs"; serpentine at the mismatched end | NXP AN10373 [VERIFIED; AN10798 NOT RETR.]; TI |
| Jogs | Each jog ≥15 mil (3× a 5 mil width). Serpentine spread S1 < 2× the normal gap S | VR: jog VERIFIED; **"amplitude ≥2W" NOT FOUND. The primary rule is a *maximum* spread** |
| Uncoupled length | Into a pin or ball **≤45 mil (1.14 mm)**; breakout within **0.25 in (6.35 mm)** of the package | **VR CORRECTED** the KiCad-forum 3.0 mm figure |
| Vias | Equal count on P and N, equally spaced, close to the SoC. USB3 ≤2, USB2 ≤4. **PCIe/SATA/HDMI 0 on AM57xx/KeyStone II, 2 on AM64x/AM65x**; CSI 2 | VR: VERIFIED+CTX / CORRECTED |
| Antipads | As large as possible (30 mil "significant benefits"), on all layers; no non-functional pads | SPRAAR7J p.12 [VR addition] |
| In-line SMDs | ≤0603, 0402 strongly preferred, placed symmetrically; void the plane 100% under the pads, ≥2 layers deep; 60% under ESD/EMI signal pads | SPRAAR7J [VERIFIED] |
| Bends | >135° (TI Rev J; older revisions said two 45° turns). NXP: ≥135°, ≥20 mil air gap, flanking segments ≥1.5W, equal left and right bends | [VR VERIFIED (updated)] |
| Constant width after BGA escape; ≥1.5W from voids | — | SPRAAR7J |

**KiCad semantics.**
- KiCad 9 `skew` is measured against the **longest** matched net, not the average (corrected in [HS]). `within_diff_pairs` tests each pair separately.
- `diff_pair_gap` is not tested on non-parallel fanout. `diff_pair_uncoupled` counts length that is non-parallel or outside the gap range.
- Pair-to-pair clearance condition: `A.inDiffPair('*') && !AB.isCoupledDiffPair()` ([KiCad 9 docs](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html) [P]).

**Unverified protocol skew limits** in kicad-happy: USB HS 25 ps, PCIe 5 ps, Ethernet 50 ps, HDMI 20 ps [P-code].

### Implications for our system
- skew_max = min(spec or vendor value, k·t_r), with k ≈ 0.1, or tighter for balanced links such as Ethernet. Convert using the per-layer delay (KiCad 10 tuning profiles; Ott's 150/180 ps/in).
- Implement **running-skew compensation**: walk both legs and insert a tune where |running skew| > about 0.2 × the budget. End totals alone are not enough.
- Add a placer cost for **direction alignment**: a pair should exit and enter in the same sense.
- Router: symmetric breakouts; serpentine switchbacks short or uncoupled; GND vias beside each differential via pair; equal via counts.
- Emit `diff_pair_uncoupled` from NXP's 45 mil and TI's 0.25 in breakout, not from forum values.

---

## 4. Interface rule packs (vendor-keyed; conflicts flagged)

*All [P] unless tagged. TI table values are scoped to the named SoC family [VR].*

### 4.1 USB 2.0 / 3.x / USB4 / Type-C

| Param | Default | Vendor variants and **conflicts** | Check |
|---|---|---|---|
| USB2 Zdiff / Zse | 90 Ω ±15% / 45 Ω ±15% ([SLLA414A](https://www.ti.com/lit/pdf/slla414)) | Qualcomm 75–105 Ω; Microchip AN26.2 90 +5/−10 Ω (Z0 40–55); AN13.10 SE 42–78 "acceptable"; SPRAAR7A SE ±10% | K class + solver |
| USB2 intra-pair | ≤1.27 mm (50 mil) ([SPRAAR7J](https://www.ti.com/lit/pdf/spraar7); [AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf)) | SPRAAR7A (2013): 2 mil; TUSB9261/SLLU149E: 150 mil; [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb-2dot0-routing-constraints.html): 2 mm. Vendor-profile resolution | K `skew within_diff_pairs` |
| USB2 length | Warn >150 mm (Microchip: "~6 in may degrade"); error >250 mm (Qualcomm) or >304.8 mm (TI J, typ. 101.6 mm) | SPRAAR7A: 4 in; SLLU149E: >8 in "contact TI". TI loosened sharply between Rev A and Rev J | K `length` + `fromTo` |
| USB2 vias / stubs / TPs | ≤4 / 0 / 0 | Legacy rule: stub <200 mil if unavoidable | K `via_count`; G |
| USB2 spacing | ≥30 mil to other nets, ≥50 mil to clocks (TI) | Microchip ≥3·max(W,H) (W 8, H 4.3 → 24 mil); Qualcomm 3W. Meanders: amplitude ≤3X, gap ≥5X | K `clearance` |
| USB2 reference | Continuous GND ≥5× pair spacing each side; parts ≥5× spacing away; no routing under parts ([AN13.10](https://ww1.microchip.com/downloads/en/Appnotes/AN13.10-Application-Note-DS00002972A.pdf)) | — | G: offset-polygon coverage |
| USB2 misc | No AC caps, no P/N swap, no branch to two connectors, short 1 kΩ stubs, PHY JTAG <6 in, SMPS kept away; TH receptacle entered from the bottom with ≥0.5 mm clearance and unused pads removed | — | M/G |
| Shield termination | **Conflict, resolution "ask":** AN26.2 330 Ω ∥ 0.1 µF at each connector; AN13.10 ground the host side only, device side AC-only; SPRAAR7A chassis strap plus ferrite 10–50 Ω at 100 MHz, optional VBUS ferrite 47–1000 Ω | — | ask |
| USB3 Zdiff | 90 Ω ±15% | AN26.2 85 ±5 Ω; AM57xx 83.7–96.3; AM65xx 95 ±5%; Qualcomm 70–100 | K + S |
| USB3 intra-pair | 5 mil (SPRAAR7J, AN26.2, SLLU149E; SLLA414A "15 ps/m, TI recommends 5 mils") | [TUSB1046](https://www.ti.com/lit/ds/symlink/tusb1046-dci.pdf) 2 mil; TUSB9261 2.5 mil; [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb3dot1-displayport-routing-constraints.html) 5 ps ≈ 0.7 mm (≈6× looser; store as the "physics-justified relaxed" option) [D] | K |
| USB3 inter-lane / DP AUX | 70 ps (10 mm) / 50 ps (7 mm) (Qualcomm) | — | K |
| USB3 loss | Connector→PHY: Gen1 ≤5.5 dB at 2.5 GHz, Gen2 ≤7 dB at 5 GHz (Qualcomm). Heck: channel −6 to −20 dB, cable ≤7.5 dB | — | S |
| USB3 vias | ≤2 per trace, plus GND return vias at each transition | Heck: "up to 1 in of routing per via"; ESD + CMC ≈ −1 in ([DevCon](https://community.infineon.com/gfawx74859/attachments/gfawx74859/usb-superspeed-peripherals/18243/1/2-4_SSUSB_DevCon_DesignGuidelines_Heck.pdf), partly legible) | K + G |
| USB3 length | 88.9 mm (AM57xx), 139.7 mm (KeyStone), 101.6 mm (AM65xx); TUSB7340 8 in | Heck: host 2–12 in, device 1–4 in (keep ≤2 in) | K / S |
| USB3 spacing | 5W between pairs and from DP/DM; 30/50 mil (TI) | TUSB1046 3W; Qualcomm 4W (Gen2) / 3W (Gen1) RX–TX, 4W others; Microchip 5X. If impossible, ground fill or opposite sides of GND (TUSB9261) | K |
| USB3 AC cap | 75–265 nF Gen2, 75–200 nF Gen1 (Qualcomm); TI controllers 0.1 µF; redrivers 220 nF TX (+330 nF RX); TUSB1046 raised DP max 200→265 nF | — | M |
| AC-cap package / void | ≤0402 (0603 absolute, 0201 OK), no C-packs, symmetric, near the connector | **Void conflict:** 100% ≥2 layers (SLLA414A) vs 60% under ESD/EMI pads (SPRAAR7J) vs 100% under CMC/ESD (Heck) | M / G |
| Chain order | connector → ESD → CMC → AC cap → PHY (all primary sources agree) | Qualcomm: AC cap near the source or the connector. TUSB1002A: cap ≥0.25 in from the redriver [S] | G: path order |
| Bends | ≥135° with balanced left/right; all pairs on one layer; TPs only in series and symmetric (TUSB1046) | — | K `track_angle` / G |
| USB4 | [S] only: 85 Ω ±7%, skew <3 mil, ~60 mm; loss budget 8.5→5.5 dB at 10G; a Gen2 8.5 dB budget gives ~5 in | No primary source | low confidence |
| Type-C CC | ≥8 mil (VCONN ≤600 mA); total C 200–600 pF (220 pF 0201 X7R example); **no passives** between PD controller and receptacle [S] | TPS65988DK minimums: CC 8, VIN_3V3 6, GND 10, GPIO 4, cap GND 16 mil [S] | K / M |
| Type-C protection | TPD6S300A: at the connector; protected and unprotected traces apart; USB2/SBU straight with largest radii; via *before* the D1/D2 pins, not onto them; VBIAS 0.1 µF. Mux: TUSB1046 connector → AC caps → redriver; no numeric mux distance; "CMC before mux" disputed [S] | — | G |

### 4.2 PCIe Gen2–6

**TI SNLA426 loss budget** (dB; [SNLA426](https://www.ti.com/lit/pdf/snla426)):

| Item | Gen3 | Gen4 | Gen5 |
|---|---|---|---|
| CPU package | 3.5 | 5 | 9 |
| 9 in system-board trace (high-loss material) | 13 | 14 | 16 |
| CEM connector | 0.5 | 0.5 | 1.5 |
| 4 in add-in card | 6.5 | 8.5 | 9.5 |
| **Total** | **23.5** | **28** | **36** |
| Crosstalk mitigation | negligible | <2 | 4–5 |
| Temperature/humidity | — | — | 2–3 |

Eye after EQ: 25 mV / 15 ± 1.5 mV, 0.3 UI.

**Loss per inch at 8 / 16 GHz** (TI SNLA426):

| Material | Dk / Df | 8 GHz | 16 GHz |
|---|---|---|---|
| Megtron 6 | 3.4 / 0.002 | 0.189 dB | 0.336 dB |
| Rogers | 3.48 / 0.0037 | 0.251 dB | 0.411 dB |
| GETEK | 4.1 / 0.011 | 0.548 dB | 1.017 dB |
| Nelco 4000-6 | 4.0 / 0.012 | 0.578 dB | 1.078 dB |
| FR4 | 4.4 / 0.014 | 0.686 dB | 1.289 dB |
| Tetra FR4 | 4.1 / 0.022 | 0.961 dB | 1.844 dB |

**Other loss data:**
- [Efinix](https://www.efinixinc.com/docs/an063-high-speed-transceiver-design-guidelines-v1.2.pdf) at 6.25 GHz: about 0.5 dB/in (Megtron 6), about 1 dB/in (FR4); RX maximum 25 dB.
- [EMA](https://www.ema-eda.com/wp-content/uploads/2025/10/PCIe-Design-Guide-Part-1.pdf) (an EDA reseller, lower authority):
  - End-to-end budgets: Gen3 <20 dB at 4 GHz; Gen4 <28 dB at 8 GHz; Gen5 <36 dB at 16 GHz; Gen6 <32 dB at 32 GHz (PAM4).
  - Df: <0.010 (Gen3), <0.005 (Gen4), <0.002 (Gen5).
  - "12 in of FR4 can exceed Gen5."
- NXP AN10373 (2005): 0.35–0.50 dB/in and 1–5 ps jitter per inch; add-in ≤4 in, system board <12 in.
- NXP AN12864: Gen4 1.0–1.2 dB/in [S].

| Param | Default | Variants / **conflicts** | Check |
|---|---|---|---|
| Zdiff | 85 Ω for CEM add-in; the spec allows 70–100 Ω | TI SoC tables: **100 Ω ±10% (AM57xx/KeyStone), 95 Ω ±5% (AM64x/AM65x)** [VR]; Qualcomm 70–100; SLLU149E 100 Ω / 50–55 Ω SE; REFCLK 100 Ω, ≤200 fs RMS RJ | K + S |
| Intra-pair | ≤5 mil, **additive over segments** (SLLU149E, SNLA426, Efinix) | Qualcomm 5 ps ≈ 0.7 mm; EMA ±2 mil (Gen4–6) | K, per `fromTo` segment when caps split the pair |
| Lane-to-lane | Not required (SNLA426: "typically up to 1 inch"; §13 also says "<6 in", an internal inconsistency); Qualcomm: no REFCLK/TX/RX matching | SoC tables: RX and TX groups ≤550 mil (AM57xx/KeyStone) or 6 ns RX / 1.5 ns TX (AM65xx) | emit only on device demand |
| Single-board budget | Gen2 −6 dB at 2.5 GHz / 250 mm; Gen3 −10 dB at 4 GHz / 300 mm ([Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/PCIe%20layout%20guidelines.html)) | SLLU149E Gen2 20 in on FR4; Efinix add-in ≤101.6 mm; TI SoC 4700/5500/4000 mil | S |
| Via cost | ≈2 in of length per via (Gen2 FR4; 6 vias → 8 in) (SLLU149E) | Heck ≈1 in (5 Gb/s) | loss score |
| Via geometry | 10/20/40 mil drill/pad/antipad; via-in-pad preferred; NFPs removed (TI) | EMA 8–10 / 18–22 / 30–35 mil | G |
| Return vias | Within 50 mil (TI Gen5) | ≥2 within 100–200 mil (EMA); 200 mil (TI general) | G |
| Stubs | <15 mil preferred; Gen5 hard max ≈51–54 mil | EMA: 20 mil resonates at 8–16 GHz | G |
| AC-cap value | **Conflict:** TI 75–220 nF; Qualcomm/Efinix/NXP Gen3+ 176–265 nF; Gen2 75–200 (265) nF; SLLU149E 0.1 µF 0402 | **220 nF satisfies every range**; BOM window 176–220 nF [IF] | M |
| AC-cap position | **Conflict:** chip-to-chip near RX (SNLA426); same board near TXP/TXN (SLLU149E); TX side (Efinix); either end (Qualcomm). All agree: near the connector for add-in/edge finger; never mid-line or staggered; pair caps side by side | Treat "within N mm of either endpoint" as satisfied | G |
| Cap package / void | Smallest (0201 pad 12 mil vs a 5–7 mil 85 Ω trace); void 100%, 2 layers, larger than the pad | Efinix: 0201 | G / M |
| Plane edge / voids | ≥max(5W, 5H) from the plane edge; ≥4H from voids; pairs 4–5H apart | Qualcomm 4W (Gen3), 3W RX–TX (Gen2); EMA ≥3W (≥4W for Gen6); Efinix ×5 | K / G |
| Serpentine | Segments ≥max(3W, 3H); at the source or mismatched end (SNLA426, Qualcomm) | — | G |
| Edge fingers | No inner copper within 0.381 mm below the fingers; planes ≤2 mm into the finger footprint (Efinix, citing CEM 4.0) | — | G |
| Microstrip vs stripline | **Conflict:** SPRAAR7J "does not recommend stripline"; SNLA426 and Efinix favour coupled stripline or TX and RX on different layers at Gen4–5 | — | selector |
| Clock buffer | No parts or vias between the two lines; 0402/0201; same layer and via count; "1 mm ⇒ 6 ps"; GND via at each layer change; ≥3W to others (5W optimal); one GND via per decap (Renesas) | — | G |

**Inference [D]:** L_max ≈ (budget − Σ via/cap/connector allowances) / dB-per-inch at Nyquist.
- Qualcomm's two points imply about 0.85 dB/in at 4 GHz and 0.6 dB/in at 2.5 GHz.
- TI FR4 at 8 GHz with Gen4's 14 dB gives about 20 in before vias, or realistically 9–12 in, and much less for Gen5.
- **Store budgets and material tables, not millimetre limits.**

### 4.3 DDR3 / DDR4 / LPDDR4 (controller-keyed)

| Group | TI | Others | Check |
|---|---|---|---|
| DDR3 impedance | 50 Ω ±5% SE; 100 Ω ±5% DQS/CK ([SPRABI1D](https://www.ti.com/lit/pdf/sprabi1)) | PolarFire: Z0 50, Zdiff 100 | K |
| DDR3 ADDR/CMD fly-by | ±20 mil (0.51 mm) to CK *at each SDRAM*; equal vias per segment; stubs <80 mil; stub skew ±10 mil | [Micron TN-41-13](https://cdn.hackaday.io/files/19354828041536/tn4113_ddr3_point_to_point_design.pdf) ±1 mm; Intel ±20 ps [S]; PCBWay ±25 mil, stubs <200 mil [S] | K `skew` + `fromTo` per SDRAM |
| DDR3 CK | ±1 mil per SDRAM; stubs <40 mil; AC VTT termination at the end | — | K |
| DDR3 byte lane | DQS ±1 mil; DQ/DM ±10 mil; ≤2 vias, equal across the byte; one layer per byte; no mid vias; ODT only; bit swaps within a byte allowed | Micron ±0.5 mm (data); Intel ±10 ps (FPGAs cannot deskew >20 ps) [S]; ISSI ±10 ps ≈ ±50 mil [S] | K + G |
| DDR3 spacing | ≥5W centre-to-centre including serpentines (4W allowed, not above 1066 MT/s); match by stripline-equivalent length | — | K |
| DDR3 termination | 39–42 Ω (39 Ω 1%) to VTT = 0.75 V at the last SDRAM, ≤500 mil | — | G |
| DDR3 VREF / VTT | ≥30 mil wide, ≥15 mil to others, top layer, GND-shielded; 0.01 + 0.1 µF at each pin, 0.1 µF at the source; ±1%. VTT regulator near the SDRAMs, VTT island, 0.1 µF per pin + 10–22 µF | — | K + G |
| DDR3 write leveling | ≤2500 ps; DDR3-1333 example <2135 ps (or <1385), >365 ps, at 180 ps/in | — | S |
| DDR4 CK/ADDR segments | A1+A2 ≤500 ps (skew ≤3 ps); A3 ≤125 ps; AS 5–17 ps (skew 1.3–3); AT ≤75 ps (skew ≤14); CK P/N ≤0.4 ps per segment, ≤0.8 ps total; CK↔ADDR_CTRL ≤4 ps per SDRAM; ≤3 vias (difference ≤1); 4w / 3w spacing (2w within ≤500 mil of ends); Rcp = Zo ±1 Ω, Rtt = Zo ±5 Ω; **no series termination** ([SPRAD06C](https://www.ti.com/lit/pdf/sprad06)) | [Microchip PolarFire](https://onlinedocs.microchip.com/oxy/GUID-FF8061A7-7A15-470F-A6F5-E733C24D85F0-en-US-11/GUID-07D00815-AB98-4174-B330-DAD67471AD0C.html) ≤1600 MT/s: ADDR/CMD↔CK **±100 ps**; R_T 30–50 Ω; ODT 80/120/240 | K `length`/`skew` in ps + `fromTo` |
| DDR4 data | BYTE ≤500 ps; DQS P/N ≤0.4 ps; **DQS↔DQ ≤2 ps**; ≤2 vias (difference 0); cross-byte matching "neither required nor recommended"; byte swaps OK; bit swaps only without CRC; 1 ps ≈ 5 mil | PolarFire **±25 ps** (read training absorbs the rest); Intel Agilex 5 ±3.5 ps, DQS-DQS <1 ps [S] | K |
| DDR4 VREF / VTT | VREFCA 20 mil with 0.1 µF per pin; VTT sub-plane at the end; VTT optional with one device, but CK termination still required | — | G |
| LPDDR4 CA | ≤450 ps (Dk 3.7–3.9, Df 0.002); **CK P/N ≤0.75 ps**; ADDR_CTRL vs CK ±312.5 ps die-to-pin; ≤3 vias; stub ≤20 mil; 5w / 3w | — | K + G |
| LPDDR4 data | ≤450 ps; CK − DQS = 0 to 3 tCK; DQS P/N ≤1.5 ps; DQS↔BYTE ≤150 ps; shortest DQ − DQS ≥ −49 ps; ≤2 vias; stub ≤40 mil | — | K |
| Policy | **Match to <20% of each limit in the tool, keep the full limit as max, then run IBIS PVT simulation** (SPRAD06C) | Micron: budget ≈1% of the clock period (±1 mm address, ±0.5 mm data at 800 MHz; 6.5 ps/mm; outer layers ~10% faster; ≤20 ps per via; 10 ps ⇒ 1.5 mm) | pack policy |

**Delay-to-length conversions differ:** TI SPRAD06C 1 ps ≈ 5 mil; SPRABI1D 180 ps/in ≈ 5.6 mil/ps [D]; Micron ≈ 6.1 mil/ps [D]; Renesas 1 mm ≈ 6 ps; NXP 6 mil/ps for packages [S]. **Use the KiCad 10 stackup delay model instead of any one constant.**

### 4.4 Ethernet 10/100/1000BASE-T and RGMII

| Param | Value | **Conflicts** / notes | Check |
|---|---|---|---|
| MDI Z | 100 Ω ±10% ([SNLA387](https://www.ti.com/lit/pdf/snla387)) / ±15% ([Pulse](https://www.farnell.com/datasheets/2699973.pdf)); 50 Ω SE | Pulse: pairs <30 mil edge-to-edge lower Zdiff by up to 10 Ω | K + S |
| MDI length | TI total <2 in | Microchip [AN2054](https://ww1.microchip.com/downloads/en/Appnotes/00002054A.pdf) and Pulse: total <4 in | K `fromTo` |
| Skew | Intra-pair 20 mil (1G) / 50 mil (10/100) (TI); AN2054 <50 mil intra, <600 mil inter; Pulse 50 mil | Johnson: magnetics balanced to 1:1000 gives a ≈0.1" budget | K |
| Vias | ≤2 per trace, matched; ideally none, no crossovers (AN-1469) | — | K |
| Spacing | TI ≥30 mil between pairs; Pulse TX–RX ≥50 mil (100 preferred); digital ≥300 mil (Microchip, Pulse) | — | K |
| **PHY↔magnetics** | **Pulse ≥25 mm "for EMI"** vs **Microchip <1 in (≤3 in max)** vs TI total MDI <2 in; TI forum PHY→RJ45 ≲3 in [S] | Soft window: target ~25 mm, error >76 mm [IF] | G + vendor switch |
| Magnetics↔RJ45 | <1 in / <25 mm (all sources) | — | hard |
| Edge | Pulse: PHY and TX pairs ≥25 mm from the edge (figure: ≥1 in, 2 in preferred; silicon 1–4 in from the connector); traces > trace height from the board edge | — | G |
| Voids | Void only under in-line parts (magnetics, chokes, AC caps, ESD): 2 layers standard, all layers automotive, ~20 mil margin. No metal under magnetics (integrated RJ45 excepted). AN2054: clear planes from mid-magnetics to RJ45 (HV barrier) | — | G keep-outs |
| Bob Smith | 75 Ω + 1000 pF ≥2 kV (TI) / 3 kV (Microchip; or 1500 pF / 2 kV); ≥50 mil around the cap; not for PoE | — | M + K |
| Chassis | Isolate by ≥20 mil keep-out on all layers, bridged by a cap + ≥1 MΩ (SNLA387); or two 1206 0 Ω on either side of the RJ45, swappable for caps or beads at EMC test (AN-1469, DP83867); 2–3 1206 pads (AN2054); never overlap chassis and circuit planes | — | K `clearance` GND↔CHASSIS |
| **ESD location** | **TI SNLA387: PHY side of the magnetics** (common-mode swings on the cable side) **vs generic: at the connector** (SLVA680A) | Pack parameter | vendor switch |
| PHY misc | 49.9 Ω 1% terminations and 0.1 µF near TD/RD; MII/RMII <6 in, matched within 2 in; 25 MHz crystal C_L1 ≈ 2C_L − 7 pF (start at 33 pF); no floating metal; ≥4 layers (6 recommended); bypass pad-to-via <10 mil | — | M / G |
| RGMII ([DP83867](https://www.ti.com/lit/ds/symlink/dp83867ir.pdf)) | 50 Ω; TXD/RXD skew <11 ps (~60 mil); <2 in recommended, <6 in max | — | K ps |

### 4.5 HDMI, DisplayPort, MIPI D-PHY, SATA, UFS

| Interface | Values | Conflicts / notes |
|---|---|---|
| HDMI TMDS | 100 Ω ±15%; **no AC caps**; no polarity swap; intra-pair ≤0.15 Tbit, inter-pair ≤0.20 Tchar (6 Gb/s → ~25 ps [D]) (SLLA414A). TI SoC: 90–110 Ω, ≤4000 mil, ≤5 mil, **0 vias**. Retimers: top layer, controls on the bottom. TPD12S016: ESD at the connector, no vias connector→TVS, no 90° turns | ADI ADV3003 inter-channel ≤0.05 in [S]; Intel ±10%, ≤2 vias [S] |
| DisplayPort | 100 Ω ±10%; AC caps required; intra-pair ≤20 ps (~5 mil) (TI) | Qualcomm 5 ps intra, 70 ps inter, 50 ps AUX. Caps: 75–200 nF (DP 1.2) vs 75–265 nF (newer TI, Qualcomm 10G) |
| MIPI CSI D-PHY ([Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/mipi-csi-d-phy-routing-constraints-up-to-2dot5-Gbps.html)) | 70–100 Ω / SE 36–52 Ω; intralane 0.7 mm, interlane 1.4 mm; spacing 2.5W to others, 1W intralane, 1–1.5W interlane | TI AM62x: ≤10 in, 85–115 Ω, **loosely coupled** (LP mode), intra-pair ≈ UI/50 (8 ps at 1.25 GHz [D]), lane ≤40 ps (0.1 UI), ≤2 vias |
| D-PHY max trace vs rate | 0.5 / 0.75 / 1.0 / 1.5 / 2.1 / 2.5 Gb/s: IL −2.1 / −2.3 / −2.3 / −2.5 / −3.5 / −6.5 dB. Better cable: 260 / 210 / 200 / 145 / 170 / 210 mm. Worse cable: 190 / 155 / 125 / 60 / 90 / 150 mm | Non-monotonic because each row assumes a 3 in or 6 in flex → **the pack needs a `cable_il_db` input** |
| SATA | 100 Ω ±15%; ≤2.5 mil; caps ≤0402 near the connector, no C-packs; TX↔RX 5W; **P/N swap allowed** (TUSB9261) | SPRAAR7J: 85–115 Ω, ≤3500/5500 mil, ≤5 mil, 0 vias. TDA2 caps 0.3–12 nF (typ. 10 nF) [S]. LattePanda: **no** polarity inversion, caps ≤10 mm from the connector [S] → controller-dependent |
| UFS (Qualcomm) | G3 6 Gb/s: −6 dB at 3 GHz, 25/75/150 mm, 75–105 Ω. G4 10 Gb/s: −1.3 dB at 2.9 GHz / −5.0 dB at 5.8 GHz, ≤70 mm, 70–110 Ω. Intralane 5 ps (0.7 mm); lane–lane 30 ps (4.2 mm); RX–TX 1.5–3W, others 2–3W | — |

UI-based budgets (HDMI, D-PHY) are stored as **formulas**, resolved to ps at the configured rate, then to mm through the KiCad 10 per-layer delay.

### 4.6 CAN, RS-485, I2C, SD/SDIO, SPI/QSPI, slow clocks

| Bus | Rules |
|---|---|
| CAN ([SLLA270](https://www.ti.com/lit/pdf/slla270), [TCAN1042H](https://www.ti.com/lit/ds/symlink/tcan1042h.pdf)) | 120 Ω only at the two physical ends, or a split 2 × 60 Ω ±1% + 4.7 nF (3 dB at 1.1 Mb/s). Termination must not vanish when a node is removed. 40 m at 1 Mb/s, ≤30 nodes, stub ≤0.3 m. Length/rate: 100 m at 0.5 Mb/s, 200 m at 0.25, 500 m at 0.1, 1000 m at 0.05; above 100 m, rate × length ≤ 50. Stub ≤⅓ critical length (50 ns edge, 5 ns/m → 1.67 m; 160 ns slope → ~5.3 m). TVS/varistor, filter caps and CMC at the connector, **in the signal path** ("do not force the transient current to divert"); ≥2 vias on bypass and protection grounds |
| RS-485 ([SLLA272D](https://www.ti.com/lit/pdf/slla272)) | 120 Ω at each end (2 × 60 Ω low-pass in noisy environments). Stub electrical length <1/10 of the driver's 10/90 t_r, i.e. L ≤ t_r·v·c/10 (1 Mb/s/100 ns → 7 ft; 250 kb/s → 19 ft; 200 kb/s/500 ns → 38 ft). Failsafe 2 × 523 Ω at 5 V; 32 UL; length × rate <10⁷; both lines close and equidistant |
| I2C ([SLVA689A](https://www.ti.com/lit/pdf/slva689)) | t_r max 1000 / 300 / 120 ns; C_b max 400 / 400 / 550 pF (Sm/Fm/Fm+). R_P,min = (VCC − 0.4)/3 mA; R_P,max = t_r/(0.8473·C_b). Fully automatable from stackup pF/mm plus pin capacitance (NXP UM10204 itself was blocked) |
| SD ([Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/SDC2%20external%20SD%20card%20routing%20constraints.html)) | 50 MHz DDR / 100 MHz SDR: 10 pF, <150 mm, CLK↔data 6 mm. SDR104 at 208 MHz: 5 pF, <50 mm, 2 mm. Spacing 1.5W; CLK series R 18–27 Ω at the source |
| SDIO ([Espressif S3](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html)) | CMD/DATA within ±50 mil of CLK; ≤2000 mil total; CLK surrounded by GND; 50 Ω ±10% [VR] |
| QSPI 133 MHz ([Infineon AN240090](https://www.infineon.com/assets/row/public/documents/10/42/infineon-an240090-design-and-layout-guide-for-cyrs17b-cyel17b-flash-quad-devices-applicationnotes-en.pdf)) | IO ±30 mil, SCK–IO ±200 mil, ±1500 mil (exact meaning per the source) [S, first pass] |
| Slow multi-drop clock (Qualcomm SLEEP_CLK) | Star branches differ by <30 mm; daisy-chain stubs <7 mm |

On a PCB, the CAN and RS-485 stub limits matter only for daisy-chained connectors. The useful local checks are "termination only on end nodes" and "protection in the signal path at the connector". No primary TVS-to-connector distance exists for CAN or RS-485.

### 4.7 Clocks and crystals

| ID | Rule | Value | Source |
|---|---|---|---|
| XTAL-DMAX | Crystal + caps to the oscillator pins | ≤12 mm (½ in), same side, load caps adjacent | [Microchip dsPIC33AK](https://onlinedocs.microchip.com/oxy/GUID-E48B4A26-F201-4F0A-BCBA-16461582816A-en-US-4/GUID-AA04B64F-3C38-4E1C-8B51-49DE3CFE2419.html) [P] |
| XTAL-DMIN | Crystal to the chip's clock pin (vendor-specific *minimum*) | ≥2.7 mm (ESP32), ≥2.0 mm (ESP32-S3); dense GND vias around the clock trace; **no vias on the clock in/out traces** [VR] | [Espressif](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html) [P] |
| XTAL-PAR | Parasitic budget | XIN–GND 1 pF, XOUT–GND 2 pF, XIN–XOUT 0.5 pF (AVR186); stray 2–5 pF (AN826); C_SHUNT 4.5 pF (TUSB9261); ~3.5 pF implied (AN-1469); 2–3 pF internal + 7 pF external = 9 pF (SWRA495L) | [AVR186](https://www.insidegadgets.com/wp-content/uploads/2013/02/Best-Practices-for-the-PCB-layout-of-oscillators.pdf), [AN826](https://ww1.microchip.com/downloads/en/AppNotes/00826a.pdf) [P] |
| XTAL-SENS | Pullability | 0.175 pF × 45 ppm/pF ≈ 7.8 ppm; LSE C_L ≥6 pF (7 pF compromise); gain margin >5; PC13 toggling shifts the LSE; Cs = pin + PCB parasitic | [ST AN2867](https://ecsxtal.com/store/pdf/stm32-microcontroller-application-note.pdf) [P; VERIFIED, no mm values] |
| XTAL-GUARD | Guard | Grounded pour or ring, no foreign nets inside or on the adjacent layer, tied to MCU ground; broken guard sections tied to a mirrored layer; no traces under the crystal on 2-layer boards; Espressif top-layer keep-out ring if ground is sufficient | Microchip, AN2867 ("essential"), SLAA322D, Espressif |
| XTAL-CAP | Caps | XIN cap first and closest; C0G; short symmetric crystal→CL1→CL2 loop with grounds close together; never route ground between the caps; cap grounds kept clear of USB/RS-232/LIN/PWM/power returns; series R near the chip side | AVR186, [SLAA322D](https://www.ti.com/lit/pdf/slaa322), Espressif |
| XTAL-SEP / TP / MAG | Placement keep-aways | XIN and XOUT apart; avoid test points; coat for humidity; "no magnetic components nearby"; no HS traces under or near crystals, oscillators, SMPS, magnetics or mounting holes | AN2867, Espressif, SPRAAR7J |
| **XTAL-CAN** | Metal-can grounding | **Conflict:** ST says do not tie it to oscillator ground; TI/AVR say housing to ground; TUSB9261 says VSSOSC must not connect to the plane | vendor switch |
| **Copper under the crystal** | — | **Conflict:** solid ground (Microchip, AVR186, SLAA322D, SWRA495L, Espressif, Nordic) vs "cut planes" (TI CDCE925 [S]) → ground for an MCU Pierce; cut only if the datasheet says so | — |
| CLK vias | — | Fully surrounded; C-shaped GND ring at every clock/RF transition (Qualcomm); clock driver adjacent to its oscillator (LearnEMC); crystal ≥5 mm from the edge and ≥10 mm from cable connectors (emcvisual, citing Infineon AP24026 and ST AN2867 [P-code]) | — |

No primary source gives a numeric crystal-to-switch-node distance. The 3 mm hs_keepout in [IF] is [D], uncalibrated. ≤5 mm is a heuristic [VR].

### 4.8 Switching-regulator pack (IF §8; overlaps the power digest)
- **Input capacitor.** MPS: Cin **<2 mm** from the chip, and the VCC cap <2 mm on the same layer — the only numeric primary Cin value ([AN065](https://media.monolithicpower.com/document/PCB_Layout_Design_Guidelines_for_NB67xSeries.pdf)). MPS also asks for:
  - ≥2 vias on the AGND–PGND tie; ≥4 vias VCC cap→AGND and 8 cap→PGND (NB675);
  - 10/20 mil vias on VIN/PGND, with 1–3 under the pins and >20 between the input caps;
  - the FB divider next to the FB pin with no vias;
  - a ≥4-layer board with Inner1 = PGND only.
- **Rohm** ([60AN066E](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf)):
  - CBYPASS 0.1–0.47 µF on the top layer; bulk Cin may be about 2 cm away; "even 1 mm" of shortening matters.
  - **Cin–Cout grounds 1–2 cm apart.**
  - Thermal vias 0.3 mm at about 1.2 mm pitch; power traces >1 mm/A (1 oz) or >0.7 mm/A (2 oz).
  - Via L ≈ (h/5)(ln(4h/d) + 1) nH.
- **Loop anchors:**
  - TI [SNVA803](https://www.ti.com/lit/pdf/snva803): a lateral loop of about 20 mm² is >1 nH; a vertical loop of 2 mm² is <0.5 nH, with about 4 V less overshoot.
  - [EPC](https://epc-co.com/epc/documents/papers/Optimizing%20PCB%20Layout%20with%20eGaN%20FETs.pdf): 0.4→2.9 nH costs >4% efficiency; overshoot is 100% of Vin at 1.6 nH versus 30% at 0.4 nH.
  - [SLYT682](https://www.ti.com/lit/pdf/slyt682): 5 A/ns × 2 nH = 10 V; L2 shield with a 5 mil core; top-layer keep-out under the inductor.
  - ADI AN-139: a 10 cm loop at 27 MHz is 187 nH single-layer, 42 nH at 1.5 mm over a plane, 13 nH at 0.12 mm, so a next-layer plane gives >3× less inductance.
- **TI layout rules:**
  - SLYT614 placement order: Cin → L → Cout → small-signal; 1 via per amp.
  - LM10504: SW trace ≤100 mil wide.
  - SLVA773: FB not parallel to SW.
  - LM5163: shield FB on another layer when R_FB >100 kΩ [S].
- **Conflicts:**
  - Cin/Cout ground: Rohm (apart) versus TI and MPS (short common return).
  - Copper under the inductor. VR: CONTESTED between Rohm and TI.
- **Loop-area tiers [D]:** ≤2 mm² excellent, ≤10 mm² acceptable ([S] blog), >20 mm² fail. VR: no primary pass/fail exists, so treat the tiers as soft.

### 4.9 Fab, assembly and mounting-hole profile (IF §10)

| Parameter | JLCPCB 2L (rec/abs) | JLCPCB multilayer | PCBWay | OSH Park 2L / 4L |
|---|---|---|---|---|
| Trace/space (1 oz) | 0.10/0.10 | 0.09/0.09 (3 mil in BGA fan-out) | 0.10/0.10 | 0.152 / 0.127 |
| Drill | 0.2 preferred / 0.15 | same | 0.15 (≥0.2 avoids surcharge) | 0.254 |
| Annular ring | 0.25 / 0.18 | 0.20 / 0.15 | 0.15 | 0.127 / 0.102 |
| Copper to edge | 0.2 routed, **0.4 V-cut** [VR VERIFIED] | same | 0.20–0.25 | 0.381 |
| Silk | ≥0.15 mm line, **≥1.0 mm text** [VR CORRECTED], 0.15 pad-to-silk | same | 0.15 / 0.8 mm | 0.127 |

**More JLCPCB limits** ([JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities)):
- Via 0.15/0.25 mm; via hole-to-hole 0.2 mm, pad hole-to-hole 0.45 mm.
- PTH-to-track 0.28 mm (0.35 recommended); mask bridge 0.10/0.13 mm.
- SMT panels: 5 mm rails, 2 mm tooling holes, 1 mm fiducials at 3.85 mm.
- Assembly pitch 0.35/0.40 mm.

**Other fab and mounting data:**
- Eurocircuits: IPI = IAR + 0.075 mm (≥0.200 mm); connected NPTH ring ≥0.30 mm.
- Mounting holes: RP2040 reference "NPTH FD2.75 SM3.15 **KO6mm**" ([RPi](https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf) [P]); other Pi boards KO 6.2 mm. M3 clearance 3.2/3.4/3.6 mm [S].
- TI: no HS traces near mounting holes. Derived keep-out Ø = max(head or standoff + 2 × 0.5 mm, vendor example).
- Assembly spacing has only secondary sources. Fab packs set only `min` (precedence 10); interface packs set `opt`/`max` and may never relax a fab minimum.

### 4.10 Vendor-spread summary

| Quantity | Tightest | Loosest | Ratio |
|---|---|---|---|
| USB3 intra-pair | 2 mil (TUSB1046) | 0.7 mm / 5 ps (Qualcomm) | ~14× |
| USB2 intra-pair | 2 mil (SPRAAR7A, 2013) | 150 mil (TUSB9261) | 75× (historic) |
| DDR4 DQ↔DQS | 2 ps (TI AM62x) | 25 ps (PolarFire) | 12.5× |
| DDR4 ADDR↔CK | 4 ps (TI) | 100 ps (PolarFire) | 25× |
| Ethernet PHY↔magnetics | <1 in (Microchip) | ≥25 mm (Pulse) | opposite directions |
| PCIe AC cap | 75–220 nF (TI) | 176–265 nF (Qualcomm) | 220 nF fits both |

### Implications for our system
- Key every pack by **vendor profile**. When the vendor is unknown, use the tightest [P] value plus an `info` finding naming the alternatives.
- **Store physics budgets, not millimetre limits:** dB budgets, dB/in tables, per-via (≈1–2 in) and per-component (ESD + CMC ≈1 in) penalties, UI formulas, and the cable IL input. Then compute L_max per stackup.
- **Delay packs** (DDR, HDMI, D-PHY, RGMII, SD) emit ps rules, with `opt` = 20% of the limit and `max` = the limit. **DDR fly-by needs one `fromTo` rule per SDRAM per group.**
- **Placement intents** come from the packs: in-line chain order (connector→ESD→CMC→AC cap→PHY); distance windows (crystal annulus, Ethernet ~25 mm window); end-node termination; AC cap at either endpoint.

---

## 5. EMC placement: connector zoning, protection, stitching, edges

**Zoning (LearnEMC [P; VR VERIFIED, with numeric defaults added]):**
- Cabled connectors on **one edge or one corner**.
- **No high-speed circuitry between connectors** ("one of the most common problems"; Guideline #3), or else a metal chassis bonded to the plane at both connectors.
- I/O device within **~2 cm** of its connector, and one connector per device's off-board links.
- Non-I/O parts **≥2 cm** from I/O nets and connectors. The 2 cm is situational: "not necessarily the best advice in every situation".
- No unrelated traces between a connector and its device; no HF signals under I/O components.
- Clock driver adjacent to its oscillator; exclusive communicators placed together.
- Use as few vias as possible on HF nets; tie unused inputs high or low.
- The worst guideline is "grouping by type, high-speed farthest from the connector", which "produced crazy layouts". Place the parts that talk through a connector **nearest that connector**.

**I/O nets and filters (LearnEMC [P]):**
- Each I/O net should end in a series or filter component near the connector.
- If an IC drives a cable directly, it must not put more than about 1 mV of common mode on it.
- Mount filters with minimal parasitics and avoid ringing higher-order filters.
- A CMC must sit on a **balanced** pair. **Never put a ferrite on ground.**
- Ground protection that guards an IC to that IC's ground; ground board-level protection to the EMC ground.
- Steer ESD current to a metal enclosure without pulling it far onto the board. In plastic enclosures, check for arc paths through seams and slow high-impedance inputs with resistors.
- Treat every pin of a fast IC as a potential HF source (DRAM supply pins show more current than signal pins).

**TVS topology (TI [SLVA680A](https://www.ti.com/lit/pdf/slva680) [P]; VR: topology VERIFIED, millimetre distance NOT FOUND):**
- Place the TVS "as near to the connector as design rules allow", and the protected IC "much further from the TVS than the TVS is to the connector".
- No stubs, and no via between the ESD source and the TVS. If a via is unavoidable, route source → TVS first, then via (Case 1). Avoid Case 2, where the IC branch comes before the via to the TVS.
- Physics: 8 kV gives dI/dt = 4×10¹⁰ A/s, so **0.25 nH adds 10 V**.
- A 90° corner develops ≥7 kV and arcs at radii below **~2.6 mm**, so use curves, with 45° as the maximum angle. Treat the source→TVS region as a keep-out for unprotected traces.
- TVS ground: one via **immediately adjacent** to the ground pin, into a same-layer plane coupled to an adjacent plane. Example: 4 stitching vias and a chassis screw.
- Example BGA-TVS via: 0.254 mm pad, 0.152 mm drill, epoxy-filled and plated over, 0.1 mm clearance. Make GND vias as large as possible.
- The **5–10 mm TVS distance is a blog heuristic → soft**.
- emcvisual's check: flag a diode closer to the IC than to the connector, or a diode ground without a pour or via within 2 mm.

**CMCs and filters:**
- TPS case study: a choke more than 30 mm away failed CISPR 25; it passed **within 5 mm** of the DC input connector ([TPS](https://tps-elektronik.com/en/case-studies/how-to-pass-automotive-conducted-emissions-cispr-25-class-5-with-tps-split-ground-plane-and-common-mode-choke-placement-emc-layout-guidelines-for-automotive-dc-dc-converters/) [VERIFIED, case study]).
- TI: AC caps on the protected side of the CMF. Use 0402 0 Ω no-stuff footprints for an optional CMF.
- emcvisual: flag a ferrite, inductor or shunt cap on a cable line more than 10 mm from the pin.
- CAN: protection in the signal path.

**Board and plane edges (VR closed the gap with three primary numbers):**
- TI: HS pairs ≥**90 mil (2.29 mm)** from the *reference-plane* edge.
- LearnEMC: critical nets ≥**2X** from the board edge, where X is the trace-to-return height.
- u-blox: >**3W** from the ground-plane edge.
- More: TI Gen5 ≥5·max(W, H); Microchip SS ≥5W from a plane edge or split, with narrow floods terminated by vias at corners and ends; Pulse > trace height, with Ethernet ≥25 mm; [HS] centreline ≥ w/2 + 3h.
- Checker thresholds: kicad-happy < h (outer layers); EMI Guardian 1 mm; emcvisual <3h (≥1 mm) over ≥3 mm.
- Research: common-mode current rises as a trace nears the edge, and a guard band of plane copper along the edge was the most effective fix [S].
- Plane-edge offsets are zone-boundary distances on an adjacent layer. KiCad `edge_clearance` covers only Edge.Cuts.

**Stitching (CONTESTED [VR]):**
- Ott stitches the periphery of G/S/S/G as a Faraday cage. LearnEMC calls "vias around the perimeter every 2 cm" not-so-good: usually unnecessary, and a perimeter-only ring "will create a resonant cavity", so distribute vias instead.
- **No primary source gives λ/20 or 3–5 mm stitching pitch.** λ/20 comes from Ott's *aperture* red flag (6" at 100 MHz).
- TPS case: stitch splits every **10–15 mm** along the boundary (the customer had 40–50 mm and fixed it at 12 mm); "above 100 MHz the slot … acts as an effective antenna" [VERIFIED, medium authority; soft].
- Johnson: a ¼" via row for isolation; a 10:1 signal:ground via ratio.
- u-blox: a stitched ground ring at the PCB edge, with power planes kept back.
- KiCad master `PCB_VIA_STITCH` default pitch is max(2 mm, 2× via diameter).

**Grounding and chassis:**
- One solid ground. Hubing 2019 marks "more than one ground" MOST EGREGIOUS ([slides](https://r6.ieee.org/scv-emcs/wp-content/uploads/sites/111/022019ToddHubing.pdf)).
- Clearing ground out under magnetics, inverters or HV is fine; splitting or gapping it is not.
- Chassis bond: a chassis layer *overlapping* digital ground, joined by multiple SMT caps, plus one low-frequency connection. Never a single point at the I/O by default, and never at the oscillator. "Bond (at RF) everything that leaves the board"; near metal structure, "Connect to it!"
- Mixed signal (Ott): one plane partitioned with routing discipline on every layer.
  - LSB at 1 V: 8-bit 4 mV, 10-bit 1 mV, 12-bit 240 µV, 14-bit 60 µV, 16-bit 15 µV.
  - For ≥14 bits, use isolated regions that are solidly connected under each ADC, with no trace on any layer crossing the slots.
  - Test by splitting with 0 Ω jumpers every ½" and comparing.
- MT-031: >300 mV between planes risks latch-up. This check applies only when a split is deliberate.
- Renesas DA9080 mandates GND cuts between bucks, which conflicts with the one-ground doctrine → datasheet override [VR].

**Pre-compliance practice:**
- LearnEMC's 10-step review. Hold it before layout and again at the first draft.
  1. Ground structure and I/O locations.
  2. Plane extent, with no gaps.
  3. Remove ground traces or fill on other layers.
  4. Power distribution: a <0.25 mm plane pair.
  5. I/O nets.
  6. Filters.
  7. Transition-time control.
  8. Critical components (op-amp loops over a plane, PLL ferrites, never a ferrite on ground).
  9. Power inverters.
  10. Trace the current path of every test: CE, RE, BCI, RI, EFT, ESD.
- Leave **footprints for optional filters, TVS and shield cans**.
- "Blindly adhering to a list of EMC design rules" fails. Identify sources, victims and coupling paths instead ([LearnEMC](https://learnemc.com/effective-application-of-emc-design-guidelines)).
- Johnson: "real EMI problems are much too complex" for simulators; promising tools are "more like expert systems". "2× last year's design needs another 6 dB"; scan early.
- Ott: clamp-measure every cable.
- Hubing's seven errors: blindly following guidelines; uncontrolled transition times; not following currents; not identifying critical traces; more than one ground; improper decoupling; bypassing filters.

**Ott's red flags (12)** ([P](https://hott.shielddigitaldesign.com/techtips/red_flags.html)):
- clock edge <10% of the period;
- an aperture >λ/20;
- split grounds;
- traces crossing slots;
- pigtail shields;
- backshells not contacting the enclosure;
- paint in seams;
- a signal layer not adjacent to a plane;
- multiple-value parallel decaps;
- ungrounded fill or thieving;
- unshielded cables without common-mode filtering;
- a single-point circuit-to-chassis ground.

Ott's satirical "maximize emission" list, to be inverted, claims +20–30 dB ([P](https://hott.shielddigitaldesign.com/techtips/maxemission.html)).

**emcvisual placement thresholds** [P-code]:
- crystal ≥5 mm from the edge and ≥10 mm from cable connectors;
- storage inductor ≥3 mm from the edge and ≥10 mm from cable connectors;
- switch-node copper <100 mm² (<40 mm² near an edge or connector);
- hot loop flagged from 30–40 mm².

**Placement priority order** ([HS] §8):
1. Lock mechanicals, cluster the cabled connectors and mark the I/O zone.
2. Put protection, filters, CMC, magnetics and the chassis bond at the pins.
3. Put the interface ICs within ~2 cm, with a clear corridor.
4. Place critical ICs (SoC, DRAM in fly-by order, SerDes) so fast links are short, uncrossed and direction-aligned, and never between connectors.
5. Put clocks next to their consumer, away from the I/O zone and edges.
6. Partition by function over one plane, with power stages away from I/O.
7. Place in-line SI parts (series R at the driver, AC caps), then decaps and passives.

Steps 1–3 are hard, anchor-relative constraints. Steps 4–6 are soft cost terms; no primary source gives weights.

### Implications for our system
- The placer's cost terms: the MREMC "between connectors" V_cm estimate; I/O-zone intrusion; fast-net length and crossings; pair direction alignment; crystal, inductor and switch-node distance to edges and connectors.
- Encode TVS and CMC rules as **comparative constraints**: d(TVS, connector) < d(TVS, IC), with zero vias before the TVS and a GND via at its pad. Do not use millimetre limits.
- The edge rule is per layer: ≥2h from the board edge (`edge_clearance`) and ≥90 mil or w/2 + 3h from the plane edge (geometric).
- Treat stitching as a single "largest unstitched region" metric, so the perimeter-versus-distributed debate does not need resolving.
- Always place optional footprints (CMF 0 Ω, TVS, shield-can pads, chassis R/C) when compliance is uncertain.

---

## 6. Myths and context-dependent rules (encode as negative rules carrying the physics replacement)

| Slogan | Verdict | Evidence / status |
|---|---|---|
| 90° corners are bad | Negligible up to about 2 Gb/s: 8 mil 50 Ω corner ≈1 ps, 0.012 pF, ≈0.3% reflection at 100 ps. Rounding removes 21% of the corner copper; 70–90% would be needed to cancel the capacitance. Corners start to matter around 10 Gb/s and for pair skew. The myth comes from the MECL handbook (1971); 3 Ω at ~80 GHz; Bogatin 5 mil corner = 8.5 fF, no impact until >70 GHz | VERIFIED+CTX. **Exceptions:** ESD paths ≤45° or curved (2.6 mm arc); RF arcs or 135° (Espressif, u-blox) ([Johnson](https://www.sigcon.com/Pubs/edn/bigbadbend.htm); [Altium](https://resources.altium.com/p/slaying-900-right-angle-bend-dragon)) |
| 20-H rule | Shim & Hubing: far field "slightly higher" (the 3.6 dB figure is NOT RETR.). LearnEMC: helps only with power sandwiched between grounds; 2–3H suffices. **Montrose et al. 2005 (FDTD): "fact, not fiction"; 10-H may suffice; only for high-density multilayer boards with multiple power/return planes; parts negate the result** | **CONTESTED** → context switch, not a default ([Montrose](https://courseware.zcu.cz/CoursewarePortlets2/DownloadDokumentu?id=186283)) |
| Split analog/digital ground | Valid only for <100 kHz isolation at ~1000:1 sensitivity, and even then better done as a separate return on another layer | VERIFIED+CTX (Ott's ≥14-bit exception) |
| I/O ground island with a single-point tie | "One of the worst possible ways" | LearnEMC, Ott |
| Group by type, HS farthest from the connector | "More crazy board layouts than any other" | LearnEMC |
| 3W rule | A proxy for D/H; use K = 1/(1 + (D/H)²) | Johnson, Ott |
| Guard traces | See §1.5 (stripline only: end-shorted and length-matched) | **CORRECTED** (Bogatin & Simonovich) |
| Ground fill on multilayer | No function, perturbs Z0; floating fill is a red flag | Johnson, Ott |
| Perimeter vias every 2 cm | Usually unnecessary, and can create a cavity → distribute | CONTESTED (Ott does perimeter stitching on G/S/S/G) |
| Two ground planes above 25 MHz | Outdated | LearnEMC [VERIFIED] |
| Terminate beyond λ/4; series R above 1 V/ns; Z ≥ Z0/4 | Not criteria; relate delay to t_r | LearnEMC |
| Single-point at LF / multipoint at HF | Misused. At LF, limit the options; at HF, provide one good option | LearnEMC |
| Minimise all HS lengths | Not an EMC fix; "control your loop areas"; guideline-followers do worse than no-guidance designers | LearnEMC [VERIFIED] |
| Rely on slow logic | Parts get faster over a product's life → use slew-controlled logic | LearnEMC [VERIFIED] |
| Ferrite on ground | Never | LearnEMC |
| 0.1 µF ≤15 MHz / 0.01 µF above; 1 ground per 8 lines | Too narrow | LearnEMC [VERIFIED] |
| Decaps on both sides of a plane gap | "Don't gap the ground plane!" | LearnEMC |
| Ground daughterboards to chassis | Returns belong on connector pins | LearnEMC |
| Rounded pair corners remove skew | No (1.57p–2p per corner) | Johnson |
| Tighter coupling always reduces EMI | Not below about 0.5 mm | Johnson |
| Follow as many guidelines as possible | 90% compliance can be worse than 1–2 rules | LearnEMC |
| Other not-so-good guidelines | "Power/ground traces ≥3× signal width"; ground islands under ICs; "daisy chain, no stubs" ("sometimes yes, sometimes no"); "ground E-field shields in ≥2 places" ("terrible") | [VR] anti-rules |

### Implications for our system
- Each myth becomes a **negative rule** that stops the LLM emitting the slogan and points to the physics checker that replaces it.
- Scope the corner-angle rule to net classes `ESD_UNPROTECTED` and `RF50` only.

---

## 7. Hard vs soft vs explicit-selection rules ([VR] §3)

| Class | Rules | Encoding |
|---|---|---|
| **Hard: fab/assembly** | Fab absolute minimums (router targets the recommended values); courtyard non-overlap; IPC-2221B as a floor; JLC silk 1.0 mm / 0.15 mm | Board setup + `.kicad_dru` |
| **Hard: topology** (stated identically by every primary source) | No split or void crossing; ≥1.5W from voids (except voided SMD pads); all split crossings over the bridge; connector→TVS→IC with no stub, no via before the TVS, and a TVS GND via at the pad; 0 TPs and 0 stubs on SerDes; plus power and RF topology (CIN on the IC layer, 0 vias in the hot loop, FB from the COUT pad, single AGND–PGND tie where "mandatory", shunt cap through the named VSS pin, antenna keep-out polygon, no digital under RF, AGND+DGND to the analog plane) | G-checker; reject the placement or route |
| **Hard within declared scope** | Diff skew, via count, 30/50 mil keep-outs, via stub min(15 mil, 0.3/Gbps) | Activate only when the interface pack and data rate are known; carry `source_scope` |
| **Soft, strong** | Return via ≤200 mil as a hard max, with "closer is better" as the objective; ≥90 mil from the plane edge or ≥2h from the board edge; connectors on one edge; I/O within 2 cm; non-I/O ≥2 cm; plus the power items (L2 plane ≤0.13 mm, 1 via/A, C_boot ≥10·Cg, bead ≤20% of rated I, EP vias 0.3 mm at 1.0–1.2 mm) | High-weight cost terms; warnings quoting the source |
| **Soft, weak (heuristic)** | TVS ≤5–10 mm; CMC ≤5 mm; crystal ≤5 mm; CIN ≤0.5–1 mm (primary: MPS ≤2 mm); FB ≤2–3 mm; RF↔SMPS 20 mm; stitching λ/20 / 3–5 mm / 2 mm near SerDes; **2W/3W/5W multipliers (express in h and compute crosstalk instead)**; 2 cm²/W | Rank-based objectives ("closer than any other part"); never DRC errors |
| **Context switch required** | 20-H; copper under inductors; CIN/COUT ground proximity; **microstrip vs stripline** (TI vs Ott); thermal-via tenting; guard traces; "smallest cap closest"; perimeter stitching; PMIC ground cuts; **termination threshold t_r/2 vs t_r/6** | Store both variants plus a selector (power, layer count, data rate, fab, datasheet mandate); ask and log |
| **Exceptions to myths** | 90° corners only on ESD and RF nets | Net-class scoped |

**Severity recalibrations [VR]:**
- TL-5 (test points on SerDes) becomes hard.
- EMI-7's millimetre distance becomes soft; its topology stays P0.
- EMI-6's 10–15 mm pitch becomes soft; the P0 is "no crossing without a bridge or stitch".
- RF-05 splits into a hard PCB keep-out plus an enclosure clearance exported to the mechanical checklist (15 mm for ESP32).

**Schema fields:** `source_scope`, `statement_strength` (mandatory / must / should / as close as possible / good guideline) and `contested_by`. The **LLM's value-add** is turning relative source language into comparative constraints (distance ratios, rank orders) rather than invented millimetre values.

### Implications for our system
- Output three tiers: DRC errors (hard), scored warnings (soft), and **decisions the user must make** (context switches, logged with rationale).
- [D] heuristics default to warning until calibrated against vendor evaluation-board layouts.

---

## 8. Encodability: KiCad native vs custom geometric checkers vs simulation

**KiCad 9/10 native:**
- Constraints: `track_width`, `clearance`, `diff_pair_gap`, `diff_pair_uncoupled`, `skew` (vs the longest net; `within_diff_pairs`), `length` (also sets the tuner target), `via_count`, `edge_clearance`, `track_angle`, `track_segment_length`, `assertion`, `hole_size`, `annular_width`, `hole_to_hole`, `silk_clearance`, `courtyard_clearance`, `text_height`/`text_thickness`, `physical_clearance`, `via_diameter`, `disallow`.
- Conditions: `hasNetclass`, `inDiffPair`, `isCoupledDiffPair`, `intersectsArea`, `intersectsCourtyard`, `memberOfSheet(OrChildren)` (9.0.2), and KiCad 10's **`fromTo('U1-A*','U2-B*')`**.
- **KiCad 10 time domain** ([docs](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html)):
  - Delay = Σ(length × per-layer unit delay) + via delay (stackup height × via unit delay, with per-layer-pair overrides) + pad-to-die delay.
  - Profiles hold the ps targets. Recommended for DDR, PCIe and USB even on a single layer.
  - ps and length units cannot be mixed in one constraint.
  - Backdrills on vias and pads, from one or both sides, with a "must-cut" layer.
- **KiCad master (post-10)** ([keywords](https://gitlab.com/kicad/code/kicad/-/raw/master/common/drc_rules.keywords) [P-code]): `return_path`, `stub_length`, `net_chain_length`, `hole_aspect_ratio`, `microvia_stack_depth`, `net`.
  - **`return_path`** (`(constraint return_path (layer "B.Cu") (net "GND"))`):
    1. Union the zone fills on the named layer.
    2. BooleanSubtract that union from each track or arc polygon of the net chain.
    3. Report the remainder as unreferenced copper.
    4. Coalesce the flags by union-find.
    - It checks one explicit layer only. It does not check vias, detours, edges or reference changes.
  - **Net chains** bridge series components (`BoardChainBridging`). The topology gives the trunk plus stubs (branch point, length, delay).
  - **`PCB_VIA_STITCH`** has STITCH and GUARD modes and PLAIN, STAGGERED and POISSON layouts, with default pitch max(2 mm, 2× via diameter). It is exposed over IPC (`ViaStitchGuardSettings`), and a DRC test catches overlapping stitch zones.
  - Final syntax may change before KiCad 11. Whether `A.NetChain` will work in conditions is unknown.
- **IPC API (kipy, MIT):** `get_stackup()`, `get_zones()`, `refill_zones()`, `get_pad_shapes_as_polygons()`, `hit_test()`, `Zone.filled_polygons`.
  - SWIG bindings do not expose the stackup, so it is parsed from `.kicad_pcb`.
  - KiCad 10 IPC cannot create persistent custom DRC markers, so findings go to an HTML or JSON overlay with selection and zoom.

**Custom checker algorithm specs** ([HS] §11, plus geometric functions from [IF]):
- **A. Reference-layer map.**
  1. Read the stackup.
  2. For each signal layer, record both neighbours, h_up and h_down, and whether each is filled with GND or a declared reference net.
  3. The reference is the nearer filled layer. For stripline keep both, since about 75% returns on the nearer plane.
  4. Refill zones first. Lint Ott objective 1 here.
- **B. Return continuity.**
  - Fast path: master `return_path`.
  - Full path: sample the trace against a net-labelled raster or polygons. Compute the geodesic detour between entry and exit (A* on a raster, or a visibility graph) and classify it as VOID, ISLAND or SPLIT.
  - **Merge antipads and clearances into voids first.**
  - Buffer the trace by 1.5W, or w/2 + 3h. Scale severity by t_r and detour/h.
- **C. Reference-change check.**
  1. At each via or PTH pad, find the layers actually used (track endpoints within the pad radius, SMD pads hit).
  2. Map each used layer to its reference set. An unchanged set means no issue (Ott case 2).
  3. Same net on different planes: report the nearest via spanning both, with extra loop ≈ d × separation. Limit ≤200 mil, preferably 1–2 mm, scaled by rate.
  4. Different nets: find the capacitor minimising the pos→padA→padB loop, warn of 5–10 nH, and recommend re-layering.
- **D. Loop area.**
  - A = Σ length·h + detour plan-view area (shoelace) + Σ d_via·Δz.
  - Screen with Ott's E = 2.632×10⁻¹⁴f²AI/r at harmonics up to the knee, with I = V/Z0.
  - Use for **ranking only**, since the cable common-mode path usually dominates.
- **E. Crosstalk.**
  1. Spatially hash same-layer segments.
  2. For pairs within ≤5° of parallel, compute overlap and D = s + (w1 + w2)/2. Also check broadside pairs on adjacent layers.
  3. K = 1/(1 + (D/H)²) × min(1, 2T/t_r); add microstrip FEXT ∝ L/t_r.
  4. Per victim, sum the two nearest neighbours plus the next two. Use stricter budgets for I/O and analog victims.
  - EMI Guardian's (h/s)² × overlap / critical length is a cruder proxy.
- **F. Connector clustering and between-ness.**
  1. Take each cabled connector's reference point as the centroid of its ground or shield pins.
  2. Score whether they fit one edge band or corner quadrant (max pairwise distance, angular spread).
  3. For each fast net and connector pair, classify the sides and compute the MREMC L_return → V_cm → E_max.
  4. Flag within 6 dB of the limit (emcvisual), or V_cm > 1 mV (100 µV for stricter limits).
  5. Use as both a placement cost and a post-route check.
- **G. Stitching and fences.**
  1. Collect the GND vias spanning each plane pair and clip them to the overlap of both fills.
  2. Find the **largest empty circle** (the farthest Voronoi vertex) with diameter d_max.
  3. Require the cavity resonance c/(2√εr·d_max) > f_max (the knee). For apertures and fences, require d_max ≤ λ/20.
  4. Prefer distributed stitching. For a GUARD fence, measure the maximum gap along the offset polyline; the master generator can create the fence.
- **H. Via stubs.**
  1. Get z-depths from the stackup.
  2. Take the drilled span minus any backdrill, and the used span from attached tracks.
  3. Stub = plated barrel beyond the used span + pad rings + unremoved NFPs.
  4. f_res = c/(4·stub·√εr). Flag above min(15 mil, 0.3/Gbps), or if f_res < 3 × Nyquist.
  - Shares the stackup model with KiCad 10's via delay.
- **I. Other checks:**
  - I/O corridor ("no unrelated trace between connector and device");
  - TVS/filter/CMC nearer the connector than the IC, with a short GND via;
  - floating copper and metal islands;
  - clock edge-rate/period <10%;
  - series R near the driver;
  - running skew.
- **From [IF]:**
  - path order (`path_order_and_zero_vias`);
  - offset-polygon GND coverage (`gnd_zone_covers`);
  - `no_t_junctions_or_testpoints`;
  - distance windows and annuli;
  - plane-edge offset or a shrunken keep-in area;
  - loop polygon area → L estimate → overshoot = L·dI/dt (warn if >0.2 × Vds_max);
  - trace capacitance from stackup for the crystal and I2C C_b;
  - AC cap within N mm of either endpoint;
  - edge-finger inner-layer keep-outs;
  - the I2C R_P window.
- **Simulation (S):** loss budgets (Σ length × dB/in + allowances), DDR IBIS PVT, termination current (Archambeault), guard traces (3-D), MREMC as a pre-screen, and field-solved width and gap.

**Encodability matrix:**

| Rule family | KiCad 9/10 | KiCad master | External |
|---|---|---|---|
| Width/gap per layer for Z0 | native with `(layer …)` | same | S: field solve |
| Intra-pair and bus skew; DDR segments | native (ps, `fromTo`) | same | — |
| Length/delay across series parts | partial | `net_chain_length` | — |
| Uncoupled length, vias, edge clearance, angles | native | native | — |
| Return path on one layer | — | `return_path` | G: auto layer, buffers, detours |
| Reference change → via or cap | — | — | G (C) |
| Loop area | — | — | G (D) |
| Trace stubs | — | `stub_length` | G for plain nets |
| Via stubs | backdrill model only | — | G (H) |
| Crosstalk coupled length | clearance only | — | G (E) |
| Connector clustering / between | — | — | G (F) |
| Stitching / fence pitch | — | generator only | G (G) |
| Protection/filter topology; plane-edge offsets | rule areas partly | — | G (I) |

**Open-source checkers (licences matter for reuse):**

| Project | Licence | What it does |
|---|---|---|
| [jasonarnoldarnie/kicad-tools `return_path`](https://github.com/jasonarnoldarnie/kicad-tools) | **None stated (all rights reserved) → algorithm reference only** | KiCad 10 SWIG + numpy; reference = nearest filled layer by dielectric thickness; samples every 0.1 mm against a 0.05 mm raster; flags VOID (A* detour, FAIL >1.0 mm), ISLAND, SPLIT, TERMINAL, VIA (same-net stitching via FAIL >2.0 mm; different-net cap FAIL >5.0 mm), EDGE (w/2 + 3h); loop-area model; HTML glow 1/(1 + (x/h)²) to ±3h; `return_path_classes.json` overrides; plane copper only, no spreading model |
| [aklofas/kicad-happy](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md) | MIT | Agent skill (Claude Code/Codex); 44 rules in 18 categories: voids; transitions without a GND via; edge < h; stitching √(area/count) vs λ/20 at 3× the highest crystal frequency; 3H crosstalk on outer layers (≥5 mm coupled); skew→common mode; ESD path; connector filtering and ground-pin ratio; cavity; switching harmonics; PDN; 0–100 risk score with ≤3 findings per rule; band prioritisation; interface risk ranking; XY near-field probe points |
| [hap231/kicad-emi-guardian](https://github.com/hap231/kicad-emi-guardian) | MIT | KiCad ≥10.0.5 IPC plugin: plane gaps and detours; return-via radius 2 mm; parallel coupling (≤5°, ≥5 mm overlap, ≤0.5 mm spacing, uniform-grid hash); edge 1 mm; pair mismatch 1 mm; acute corners <75°; dangling stubs ≥0.8 mm; electrically long nets by route diameter (1/6); GND-pour appendage antennas (≤1500 MHz); stitching planner; dry-run, no markers |
| [tombueng/emcvisual](https://github.com/tombueng/emcvisual) | 0BSD-style | Browser TypeScript; reads KiCad 6–10, IPC-2581, ODB++ and Eagle. Biot–Savart near field with image currents. About 30 rules, each with threshold, origin and test board: return-gap ≥0.2 mm, detour ≥2 mm; ref-change; no-stitching (3 mm); edge-trace; cable-cm; io-coupling; long-line (no ≥10 Ω R within 15 mm); filters >10 mm; ESD; crystal; hot loop. Ranks findings by far-field share; claims a full-wave comparison (not reviewed) |
| [RolandWa/KiCAD_Custom_DRC](https://github.com/RolandWa/KiCAD_Custom_DRC) | **Non-commercial proprietary → reference only** | TOML rules: GND via within 2 mm of critical vias; decap within 3 mm; plane continuity sampled every 0.5 mm in a 1 mm zone; plane and board edge; 3W; connector filter topology; IEC 60664-1 creepage |
| [easyw/RF-tools-KiCAD](https://github.com/easyw/RF-tools-KiCAD) | GPL-3.0 | Via-fence generator (pyclipper), stitching, teardrops |
| rjwalters/kicad-tools | not checked | Protocol-aware pair rules emitting native constraints [S] |
| KiCad / kipy | GPL-3.0+ / MIT | — |

**Commercial references:**
- HyperLynx DRC EMI rules (parameterised): edge-rate/period, edge shield, exposed length, filter placement, ICs over split, I/O coupling, metal island, gap crossing, plane edge, reference change, via stub.
- Other checkers: EMISTREAM (NEC), IBM EMSAT (Archambeault; "hundreds of man-years" [S]), Zuken CR-8000 EMC Adviser EX.
- How they get net info: manual entry, name substrings, component-database classification, or IBIS/simulation. **Names alone are insufficient** ([LearnEMC](https://learnemc.com/commercial-emc-rule-checkers)).
- Clemson: source/path/antenna combinations are computer-identifiable from layout plus component data [S].

### Implications for our system
- **Checker priority:** B (return path), C (reference change), H (via stub), F (connector between-ness), E (crosstalk including I/O), G (stitching), I (protection, islands, edge rate), D (loop ranking).
- Reimplement from the algorithm specs. Code may be reused only from the MIT, 0BSD and GPL-compatible projects.
- Emit native constraints wherever possible: KiCad 10 ps profiles and `fromTo`; on master, `return_path` and `stub_length`.

---

## 9. Rule-pack format and knowledge-base schema

**Every machine-actionable rule needs five things** ([IF] §11):
1. A match pattern binding it to schematic objects.
2. Typed parameters with units (mm, mil, ps, Ω, nF, pF, dB, %, UI, W, H, or a formula).
3. Provenance and precedence: datasheet > vendor family > interface default > generic. **Conflicts are recorded, not silently resolved.**
4. A check backend: `kicad_dru`, `geometric`, `simulation` or `bom`.
5. A placement intent, kept separate from routing constraints: anchor, adjacent, order_along_path, distance_window, same_side, keepout_ring, orientation, max_loop_area or priority_order.

**YAML pack v0** (precedence: 10 fab < 20 interface default < 30 vendor family < 40 device datasheet):
- `pack {id, version, precedence, vendor_profile}`
- `applies_when {parts[{role, match{lib_regex, pin_functions, value_regex, class, nets}, optional}], nets[{role, match{pin}}]}`
- `parameters {name: {value|formula, unit, tol_pct, tag P|S|D, source, rev, by_vendor{}}}`
- `conflicts [{parameter, values[{value, source}], resolution: stricter|vendor_profile|window|ask}]`
- `placement [...]`, `routing {netclasses, diff_pairs, …}`, `checks [{id, backend, severity, emit}]`, `overrides`

**Resolution policy:**
1. The highest precedence wins.
2. Then `by_vendor[vendor_profile]`.
3. Then the declared resolution. The default is "stricter", which raises an `info` finding citing both sources.
4. **[S] never overrides [P]** at equal precedence.
5. [D] values default to warning until calibrated.

**Worked examples in [IF]:**
- **usb2_hs:** conn/phy/esd/cmc roles; zdiff 90 ±15% with by_vendor values; skew 1.27 mm (Qualcomm 2.0, TI USB controllers 3.81); len_warn 150 and len_max 250 (TI 304.8); ≤4 vias; 0.762/1.27 mm gaps; gnd_overhang 5 × pair gap; esd_conn_max 5 mm [D]. The shield conflict resolves as "ask". Placement: anchor the connector on the edge; order conn→esd→cmc→phy. Emitted DRU: `skew … within_diff_pairs`, `via_count (max 4)`, `length` with `fromTo`, and a USB2-vs-others clearance. Geometric: no T-junctions or TPs, GND coverage, ESD path order with a GND via within 1 mm. BOM: no series caps.
- **buck_sync:** cin_dist_max 2 mm; cbulk 20 mm; loop 2/10/20 mm²; dI/dt 5 A/ns; L1–L2 ≤0.127 mm; 1 via/A; 1 mm/A; SW ≤2.54 mm; FB ≤3 mm [D]; same-side; inductor keep-out ring. Datasheet reference-layout override at precedence 40, with the target loop area measured from the evaluation board.
- **xtal_pierce:** an annulus between dist_min (by vendor) and dist_max 12 mm; parasitic limits; hs_keepout 3 mm [D]; metal-can vendor switch; caps adjacent with CL1 first; series R near the MCU; GND ring tied once to the MCU ground; XIN/XOUT ≥3W [D]; no TPs. DRU: disallow track/via in `XTAL_KEEPOUT` for foreign nets.
- Untested syntax: the `within_diff_pairs` token form, `insideArea` naming and `track_angle` must be tested on the installed KiCad.

**Knowledge-base record** ([HS] §12 G + [VR]):
- `rule_id, family, statement`
- `numeric{value, unit, basis: mm|ps|W|h|λ|fraction_of_tr}`
- `physics_why`
- `applies_if{interface, t_r<, data_rate>, layer_type, enclosure, emission_class}`
- `severity, check_type{K,K11,G,S}, kicad_dru_template, checker_fn`
- `source_url, source_author, source_type{physics, rule-of-thumb, vendor-req, spec-req, measured, satirical-inverse}, provenance{P,P-code,S}, confidence`
- `conflicts_with[]`, plus VR's `source_scope`, `statement_strength`, `contested_by`
- Include the negative (myth) rules.

**Net classification:**
1. Regex seeds: USB/PCIe/HDMI/MIPI/DDR/QSPI/clock/MDI, `_P/_N`, `+/-`, `_t/_c`.
2. Then LLM confirmation from pin function and datasheet.
3. Then user overrides in the style of `return_path_classes.json`.
4. Assign each net a t_r, and treat every pin of a fast IC as noisy.

### Implications for our system
- A single interface/net-class table drives (1) KiCad-native constraints and (2) the Python checker suite. Every emitted rule carries `rule_id`, `source_url` and `provenance`.
- Make the packs data, not code, so vendor evaluation-board layouts can calibrate the [D] heuristics later.

---

## 10. Idea inventory

Tags: [HS] = rules_highspeed_emi.md, [IF] = interface_rule_packs.md, [VR] = verification_rules.md.

**Physics and modelling**
1. Encode physics, not slogans; store each myth as a negative rule carrying its replacement check [HS].
2. Return current flows directly under the trace; this is the basis for the continuous-reference rule [HS].
3. Use the ±1h/±3h/±10h spread to ground the edge and void offsets; 1.5W ≈ 3h [HS].
4. Treat a via through the same plane as no discontinuity, to avoid false positives [HS].
5. Merge antipads into void polygons and measure slot length perpendicular to the trace [HS].
6. Ott's four-level layer-change preference order as the router's policy [HS].
7. Return vias ≤200 mil (TI), scaled by rate: ~5 / 2.5 / 1.3 mm [HS][IF].
8. Stitching caps only at split crossings (≤1 µF); never use 1–10 nF/50 mil as primary [VR].
9. Avoid power-plane references; never overlap non-referencing planes [HS].
10. No ground traces or fill on boards with planes; connect ground by a direct via [HS].
11. A 10:1 signal-to-ground via ratio from Johnson's 3-D scaling [HS].
12. Differential pairs return per leg; apply return rules to each leg [HS].
13. Johnson's skew→common-mode formula (20% skew → 10% CM) [HS].
14. Critical length: t_r/6 flags for SI, t_r/2 must terminate (contested threshold) [HS][VR].
15. Slow edges first; default series R; transition time ≈20% of UI [HS].
16. Choose termination values for minimum harmonic current (Archambeault) [HS].
17. Stub limit = min(15 mil, 0.3/Gbps), including pad rings [HS][VR].
18. Decide the stub strategy (backdrill, outer layers, blind vias) before the stackup [HS].
19. Enter connector pads from the non-stub end; TH receptacles from the bottom [HS][VR].
20. Johnson's K = 1/(1 + (D/H)²) with saturation and aggressor summation as the crosstalk model [HS].
21. Derive spacing from a K budget: D ≥ H·√(1/K − 1) [HS].
22. Reduce crosstalk through h (stackup) before spacing [HS].
23. Guard traces only in stripline, end-shorted and length-matched; never in microstrip [VR].
24. Stricter crosstalk budgets for I/O and analog victims [HS].
25. Orthogonal routing on adjacent signal layers (TI, Ott) [VR].
26. LearnEMC's three-condition antenna model; 1 mV / 100 µV limits between antenna parts [HS].
27. The MREMC common-mode algorithm as a computable EMI estimator [HS].
28. Ott's DM and CM formulas, and the 5 µA / 15 µA cable limits [HS].
29. FCC 15.109 limits as the target for E_max [HS].
30. Consistency checks linking 1 mV, 3.6 µA and the Class B limit [HS].
31. A cavity-resonance formula for the stitching checker [HS].
32. Never use spread-spectrum clocks as references for transceivers, PLLs or RF [HS].
33. Every pin of a fast IC is a potential HF source [HS].

**Stackup**
34. Ott's four factors, five objectives, and an 8-layer minimum for all five [HS].
35. A candidate stackup library for 4/6/8/10 layers [HS].
36. An 8-step stackup selection and scoring algorithm [HS].
37. Encode Ott-vs-Hartley on the 6-layer stack as a warning with rationale [HS].
38. A penalty for forced P↔G reference changes in the stackup score [HS].
39. A plane pair <0.25 mm when ≥3 power pins share a rail [HS].
40. Power planes on one layer; gap ≥ plane-to-ground spacing (≥3 mm "maybe") [HS][VR].
41. Stackup is chosen before placement [HS].
42. Microstrip vs stripline is a context switch (TI vs Ott) [VR].
43. Route fibre-weave-sensitive traces at 10–35° or zig-zag [VR].
44. Ott's impedance and delay rules of thumb as a fallback before a field solver [HS].
45. Store fab stack and material data (OSH Park, JLC Dk) [IF][VR].

**Differential pairs**
46. skew_max = min(spec, 0.1·t_r), converted through per-layer delay [HS].
47. Running-skew compensation near the mismatch [HS].
48. Place ICs so pairs exit and enter in the same direction [HS].
49. Keep serpentine switchbacks ≪ ⅓ t_r or uncoupled; jogs ≥3W; spread <2S [HS][VR].
50. Pair spacing ≥0.5 mm buys no more EMI; choose the gap for Zdiff and density [HS].
51. GND vias pinning the planes at differential vias (XFP pattern) [HS].
52. Absolute keep-outs: 30 mil to signals, 50 mil to clocks [VR].
53. Uncoupled length ≤45 mil into pins; breakout ≤0.25 in [VR].
54. Equal via counts; family-scoped via limits (0 vs 2) [VR].
55. Antipads 30 mil; no non-functional pads [VR].
56. Symmetric 0402 in-line parts with 100%, 2-layer pad voids [VR][IF].
57. Bends >135° with balanced left/right [VR][IF].
58. Pair-to-pair clearance via `A.inDiffPair('*') && !AB.isCoupledDiffPair()` [HS].

**Interface packs**
59. Mandatory vendor profiles; use the tightest [P] value plus an info finding when the vendor is unknown [IF].
60. USB in-line chain order connector→ESD→CMC→AC cap→PHY [IF].
61. Store Qualcomm's 5 ps as the "physics-justified relaxed" USB3 skew option [IF].
62. A via-length penalty (~25–50 mm per via) in the SerDes cost model [IF].
63. Treat the ESD+CMC allowance (~1 in) as a length cost [IF].
64. USB shield-termination conflict resolved by asking the user [IF].
65. Type-C CC: width, capacitance window, no series passives [IF].
66. PCIe L_max computed from loss budget and material tables, not stored mm [IF].
67. AC cap within N mm of either endpoint; never mid-line or staggered [IF].
68. A 176–220 nF BOM window as universally safe for Gen3+ [IF].
69. Edge-finger inner-layer keep-outs (0.381 mm, ≤2 mm) [IF].
70. Lane-to-lane matching emitted only on device demand [IF].
71. DDR: one `fromTo` rule per SDRAM per group [IF].
72. Never emit cross-byte DDR skew [IF].
73. Match to 20% of each limit (opt), keep the limit as max, then simulate with IBIS [IF].
74. Micron's 1%-of-period default scaled with the clock [IF].
75. Use the stackup delay model instead of a single ps/mm constant [IF].
76. Ethernet PHY↔magnetics as a soft window (~25 mm target, >76 mm error) [IF].
77. Ethernet ESD location as a pack parameter [IF].
78. Chassis island and Bob Smith geometry as clearance rules [IF].
79. UI-based skew stored as formulas resolved at the data rate [IF].
80. A D-PHY length-vs-rate table with a `cable_il_db` input [IF].
81. SATA polarity rule is controller-dependent [IF].
82. CAN/RS-485 checks: termination only at end nodes; protection in the signal path [IF].
83. I2C pull-up window from stackup pF/mm plus pin capacitance [IF].
84. SD/SDIO CLK↔data matching and series R at the source [IF].
85. Slow multi-drop clock star and daisy limits [IF].
86. A crystal annulus placement (vendor min, 12 mm max) [IF].
87. Crystal parasitic-capacitance score from trace length × C′ [IF].
88. Crystal metal-can and under-copper conflicts as vendor switches [IF].
89. C-shaped GND via ring at clock and RF transitions [IF].
90. Buck pack: Cin <2 mm, loop-area tiers, L estimate → overshoot [IF].
91. Turn "minimise the loop" into a scoreable objective via inductance anchors [IF].
92. Datasheet reference-layout override at precedence 40 [IF].
93. Fab profiles set only min (precedence 10); interface packs never relax them [IF].
94. Mounting-hole keep-out derived from screw head + margin (RP2040 6 mm) [IF].

**EMC placement**
95. Cluster cabled connectors on one edge or corner [HS].
96. No high-speed circuitry between connectors; score it with MREMC [HS].
97. 2 cm I/O-zone defaults (device ≤2 cm; others ≥2 cm) [HS][VR].
98. An I/O corridor free of unrelated traces; no HF under I/O parts [HS].
99. I/O nets end in a series or filter part near the connector [HS].
100. TVS topology as comparative constraints, not mm [VR].
101. TVS GND via immediately adjacent; ESD-path corners ≤45° (2.6 mm arc) [VR].
102. Via-after-TVS routing (Case 1) [VR].
103. CMC near the connector (5 mm case study) as a soft target [VR].
104. Edge rules: 90 mil from the plane edge, 2X from the board edge, 3W (u-blox) [VR].
105. Plane-edge offset is a zone-boundary check, not `edge_clearance` [VR][IF].
106. Largest-unstitched-region metric reconciles perimeter-vs-distributed stitching [HS].
107. Split-boundary stitching 10–15 mm (soft) [VR].
108. Chassis bonding through an overlapping layer with SMT caps plus one LF tie [HS].
109. One partitioned ground; ≥14-bit isolated regions joined under the ADC [HS].
110. A 300 mV inter-plane check only when a split is deliberate [VR].
111. Optional filter, TVS and shield footprints when compliance is uncertain [HS].
112. Two EMC design reviews: before layout and at the first draft [HS].
113. Visualise each compliance test's current path [HS].
114. Clamp-measure every cable (Ott) [HS].
115. Ott's red flags as a lint list; invert the maximize-emission list [HS].
116. emcvisual's placement thresholds (crystal, inductor, switch node) [HS].
117. A 7-step placement priority order; steps 1–3 hard, 4–6 soft [HS].
118. Placer cost terms: V_cm between connectors, I/O intrusion, length, crossings, direction alignment [HS].

**Classification and verification**
119. Hard / soft-strong / soft-weak / context-switch tiers [VR].
120. Blog mm values become rank-based objectives, not DRC [VR].
121. Add `source_scope`, `statement_strength` and `contested_by` fields [VR].
122. The LLM turns relative source language into comparative constraints [VR].
123. Severity recalibrations (TL-5 hard; EMI-7 mm soft; RF-05 split) [VR].
124. Corner rule scoped to ESD and RF net classes [VR].
125. Contested rules (20-H, inductor copper, tenting, stripline, guards) are never defaults [VR].
126. Montrose's 20-H conditionality as the selector [VR].
127. Store per-part numbers (Espressif, u-blox) per part, not generalised [VR].

**Encoding and checkers**
128. KiCad 10 ps-domain constraints and `fromTo` for DDR and SerDes [HS][IF].
129. KiCad master `return_path` and `stub_length` emitted when available [HS].
130. Checker A: reference-layer map from stackup plus fills [HS].
131. Checker B: return continuity with A* detour, VOID/ISLAND/SPLIT [HS].
132. Checker C: reference-change via or cap proximity [HS].
133. Checker D: loop-area ranking with Ott's DM formula [HS].
134. Checker E: crosstalk extraction by spatial hash [HS].
135. Checker F: connector clustering and between-ness via MREMC [HS].
136. Checker G: largest-empty-circle stitching vs cavity resonance and λ/20 [HS].
137. Checker H: via-stub length and f_res [HS].
138. Checker I: protection topology, islands, edge-rate ratio, I/O corridor [HS].
139. [IF] geometric functions: path order, offset coverage, distance windows, loop L, trace capacitance [IF].
140. HTML/JSON overlay because IPC lacks persistent DRC markers [HS].
141. Parse the stackup from `.kicad_pcb` when SWIG lacks it; or use IPC `get_stackup` [HS].
142. Use the KiCad master via-stitch GUARD generator for fences [HS].
143. Licence gating: reuse MIT/0BSD/GPL code; unlicensed or non-commercial code is reference only [HS].
144. Rank findings by consequence (risk score, far-field share) [HS].
145. Expert-system framing (source/path/antenna) rather than full simulation [HS].

**Format and knowledge base**
146. A 5-part rule definition: match, typed params, provenance and precedence, backend, placement intent [IF].
147. The YAML pack schema with `by_vendor`, `conflicts` and `resolution` [IF].
148. Resolution policy: [S] never overrides [P]; [D] defaults to warning [IF].
149. A knowledge-base record schema with `basis` (h, λ, fraction of t_r) [HS].
150. Net classification: regex → LLM pin/datasheet confirmation → user overrides [HS].
151. Per-net t_r assignment flagged as an assumption when estimated [HS].
152. Calibrate [D] heuristics against vendor evaluation-board layouts [IF].
153. Test the emitted DRU syntax on the installed KiCad [IF].
154. Closing the loop (generate constraints → route → physics-check) is an unoccupied niche [HS].
