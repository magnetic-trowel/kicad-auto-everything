# Digest: High-Speed/SI, Differential Pairs, EMI/EMC, Stackup and Interface Rule Packs

**Sources digested:**
- **[HS]** `rules_highspeed_emi.md`, read in full.
- **[IF]** `interface_rule_packs.md`, read in full.
- **[VR]** `verification_rules.md`: §1A, the §1B crystal and edge rows, the §2 HS/EMC/RF/DFM additions, and the §3 classification. **Where VR conflicts with HS or IF, the VR value is used and marked.**

**Evidence tags:**
- [P] primary source read in full
- [P-code] read from source code
- [S] search snippet only
- [D] derived by the note's author
- VR statuses:
  - VERIFIED
  - +CTX: correct, but a condition was dropped
  - CORRECTED
  - CONTESTED
  - NOT FOUND
  - NOT RETR.: could not be retrieved

**Units:** 1 mil = 0.0254 mm; W = width; h/H = height to the reference plane; t_r = rise time; UI = unit interval.

---

## 0. Bottom line

- **One physical model.** All the primary authors (Ott, Hubing/LearnEMC, Bogatin, Johnson, Hartley, Archambeault) share it:
  - energy lives in the dielectric fields;
  - the high-frequency return flows in the adjacent plane, directly under the trace;
  - radiated EMI comes from common-mode voltage between "antenna parts" (cables, chassis) and from imbalance or skew.
  
  So encode physics, not slogans. Hubing: "a board that complies with 90% of the guidelines may be much worse than a board that complies with only one or two" ([LearnEMC](https://learnemc.com/why-you-should-be-cautious-about-using-emc-design-guidelines) [P]).
- **Vendor values for one interface differ 5–25×.** USB3 skew ranges from 2 mil to 0.7 mm; DDR4 DQ↔DQS from 2 ps to 25 ps; Ethernet PHY↔magnetics from ≥25 mm to <25 mm. Vendor profiles are therefore mandatory. When the vendor is unknown, use the tightest primary value and add an `info` finding.
- **VR: named app-note numbers mostly hold, but the condition is often dropped.** Typical lost conditions are device family, data rate, enclosure vs PCB, or a single measured part. So every rule needs `applies_if`, `source_scope`, `statement_strength` and `contested_by`.
- **Blog-only mm thresholds were never confirmed.** These are TVS ≤5–10 mm, crystal ≤5 mm, CIN ≤0.5–1 mm, RF↔SMPS 20 mm and stitching 3–5 mm. Treat them as ranked or comparative objectives, not DRC errors.
- **What KiCad covers, and what nobody covers.**
  - KiCad 10 handles most skew, length and delay natively: ps units, `fromTo`, backdrill.
  - KiCad master adds `return_path`, `stub_length`, net chains and via-stitching.
  - The rest needs custom checkers A–I (§8) or simulation budgets.
  - No public system closes the loop (constraints → route → physics check) inside KiCad.

---

## 1. Physics fundamentals: return paths, loop area, rise time, crosstalk, radiation

### 1.1 Where return current flows
- **Bogatin.** Above the frequency where ωL dominates, the return flows "directly underneath the signal currents" (lowest loop inductance) ([LeCroy](https://www.teledynelecroy.com/oscilloscope/blog/signal-return-paths-signal-and-power-integrity-tutorial/) [P]). Rule #7: "always use a continuous return path adjacent to every signal path" ([SIJ](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers) [P; VERIFIED]).
- **Ott.** The return uses the plane directly beneath, whether power or ground. Above 30 MHz (1 oz) the currents are surface currents, so a plane is two conductors ([Ott P6](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html) [P]).
- **Hartley.**
  - An L1 signal returns 100% in an adjacent L2 ground, even with 20 planes.
  - Two or three signal layers on one plane give "fields intermingling … where EMI comes from" ([Altium](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley) [P; VERIFIED as a paraphrase]).
- **Adamczyk, return spread** ([In Compliance](https://incompliancemag.com/pcb-return-current-distribution-in-a-microstrip-line/) [P]):
  - Microstrip: 50% within ±1h, 80% within ±3h, 97% within ±10h.
  - Stripline: 99% within ±3h, with about 75% on the nearer plane.
  - Since w ≈ 2h at 50 Ω, TI's "1.5 W from voids" ≈ 3h: same physics.
- **Johnson.**
  - The signals closest to a good return suffer the least ground bounce, so spread return pins ([P](https://www.sigcon.com/Pubs/edn/SpreadYourReturns.htm)).
  - 3-D scaling: a 0.063" via at 500 ps behaves like a Euro-connector at 5 ns, so it needs a 10:1 signal:ground ratio, i.e. a "carpet of vias" ([P](https://www.sigcon.com/Pubs/edn/ConnectLayers.htm)).
- **Differential pairs are not self-returning:** each leg returns under itself. In Johnson's 2.5 Gb/s XAUI case, a pair on a power plane with SMA grounds on ground gave a "horrible" eye. The fix was a ground island under the connectors (6 mil gap, pair about 12 mil apart at the crossing) ([P](https://www.sigcon.com/Pubs/edn/ReturnCurrentMatters.htm)).
- **Archambeault.** Reference-changing vias "greatly magnif[y]" common-mode current ([P](https://www.sigcon.com/Pubs/edn/ReducingEmissions.htm)).
- **LearnEMC.** The return follows the least inductance at MHz and the least resistance at kHz. "Radiation is NOT proportional to loop area": well-designed long lines need not radiate ([P](https://learnemc.com/the-most-important-emc-design-guidelines)).

### 1.2 Discontinuities: splits, slots, voids, reference changes
- **Bogatin's split "trifecta":**
  - reflection;
  - ground bounce and shared-path crosstalk;
  - EMI from the voltage across the plane.
  
  The only benefit is low-frequency resistive isolation, and only with the gap parallel to the signals and never crossed [P].
- **Ott's slot measurements** (plane voltage across 1" under a 10 MHz, 3 ns trace) ([Slots](https://hott.shielddigitaldesign.com/techtips/tips-slots.html) [P]):

  | Slot | Plane voltage |
  |---|---|
  | none | 15 mV |
  | ¼" | 20 mV |
  | ½" | 26 mV |
  | 1" | 49 mV |
  | 1.5" | 75 mV |
  | 15 holes of 0.052" over 1" | 15 mV |

  Merged antipads therefore act as a slot; isolated holes do not. Ott also suggests ordering one board etched but unlaminated, to inspect the buried planes.
- **Ott's layer-change order** ([P](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html)):
  1. Stay on one layer.
  2. Change between two layers adjacent to the same plane. A via through that plane is *no* discontinuity, because the antipad wall joins its surfaces.
  3. Change between same-net planes, with a GND via "immediately adjacent".
  4. Change between different-net planes. The return then goes via the nearest decap, adding 5–10 nH. Interplane capacitance only works "considerably above 500 MHz".
- **Return-via distance:**
  - TI: "symmetrically within 200 mils (center-to-center, closer is better)" when the GND reference changes ([SPRAAR7J p.8](https://www.ti.com/lit/pdf/spraar7) [P; VERIFIED]). The 40 mil and 1 mm figures are [S].
  - TI Gen5: within 50 mil, "as many as possible" ([SNLA426](https://www.ti.com/lit/pdf/snla426)).
  - EMA: ≥2 vias within 100–200 mil, on both sides of a pair ([EMA](https://www.ema-eda.com/wp-content/uploads/2025/10/PCIe-Design-Guide-Part-1.pdf)).
  - Renesas: adjacent, but not close enough to disturb impedance ([Renesas](https://www.renesas.com/en/document/apn/pcie-buffer-mux-layout-recommendations?r=1565126)).
  - Qualcomm: a C-shaped GND-via ring at every clock or RF transition ([CXO](https://docs.qualcomm.com/doc/80-PV086-5P/topic/CXO-and-SLEEP_CLK-routing.html)).
  - Rate scaling [IF, D]: about 5 mm at ≤5 Gb/s, about 2.5 mm at Gen3/4, about 1.3 mm at Gen5.
- **Stitching capacitors:**
  - **VR CORRECTED:** the "1–10 nF within 50 mil at GND↔PWR changes" figure is secondary only ([AtlasPCB](https://www.atlaspcb.com/blog/pcb-via-transition-return-current-path-signal-integrity/) [S]).
  - The primary TI value is for *split crossings*: "1 µF or lower … as close as possible" (SPRAAR7J p.7).
  - Ott, for slot crossings: 0.001–0.01 µF within 0.1" on each side. If both power and ground are split, no crossings at all [P].
  - u-blox gives no value ([NORA-B2](https://content.u-blox.com/sites/default/files/documents/NORA-B2-u-connectXpress_SIM_UBXDOC-465451970-3906.pdf)).
  - TI SLLU149E: bypass caps next to the vias.
- **TI SPRAAR7J:**
  - Keep ≥1.5 W from voids. VERIFIED+CTX: this applies to HS differential pairs and is waived at intentionally voided SMD pads.
  - "TI does not recommend high-speed signal references to power planes" [VERIFIED].
  - Never overlap non-referencing planes.
- **Unavoidable split:** use one bridge and route every crossing over it ([Ott](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html); [TI SLYT512](https://www.ti.com/lit/an/slyt512/slyt512.pdf) [VERIFIED]).
- **HyperLynx DRC "interrupted return path"** ([whitepaper](https://schematicsforfree.com/files/Manufacturing%20and%20Design/PC%20Board%20Design%20and%20Fabrication/PCB%20Design,%20Layout%20&%20Routing/USING%20HYPERLYNX%20DRC%20TO%20FIND%20EMI%20ISSUES.pdf) [P]):
  - Three cases: a gap crossing; running near a plane edge (board edge or large void); a reference change.
  - A P↔G change needs a capacitor; a G↔G change needs a via.
- **LearnEMC** ([PCB Layout](https://learnemc.com/pcb-layout) [P]):
  - A gap crossing is a *conducted* common-mode source that drives the cables on either side.
  - With solid planes, put no ground traces or fill on other layers; connect with a via straight to the plane.
  - Never filter by routing over a gap, or by putting a ferrite on ground.
  - Clemson: longer gaps mean more common-mode current [S; NOT RETR.].

### 1.3 Radiation mechanisms and thresholds
- **Antenna model (LearnEMC).**
  - An antenna needs two parts that are not electrically small, with a voltage between them.
  - Below about 100 MHz, only cables and the chassis count. Above it: tall parts, heatsinks, seams and sparse planes. ICs, traces and dense planes are poor antennas.
  - **About 1 mV between antenna parts can fail Class B; 100 µV may be needed for limits stricter than CISPR 32 B** ([P](https://learnemc.com/pcb-layout); VERIFIED).
- **Connector-to-connector magnetic coupling.** The return flux wraps the plane, so "tens of mA at tens of MHz" induces mV. The effect grows with trace width and height; stripline produces none. Fix: connectors on one edge, or a chassis bonded at both connectors.
- **MREMC algorithm** ([CMode_algr.js](https://learnemc.com/ext/calculators/mremc/calculator/CMode_algr.js) [P-code], Hubing/Su/Zhu):
  - L_ret = (µ0/π)·t·l_t/w_e/√(1 − 4(1 − 2t/w_e)·offset²/w_e²), where w_e = d1 + d2 (distances to the board edges) and offset = |d1 − d2|/2.
  - L_trace = √(µ0ε0)·l_t·Z0, and imbalance h = L_ret/(L_ret + L_trace).
  - V_cm = h·V_dm (voltage-driven), or 2πf·L_ret·I_dm (current-driven; I_dm = V/R_L or V·2πf·C_L).
  - E_max = F_max·0.55·V_cm·boardfactor·cablefactor, with:
    - boardfactor = sin(2πL_eff/λ) for λ ≥ 4L_eff, else 1;
    - cablefactor = sin(2π·1 m/λ) for λ ≥ 4 m, else 1;
    - F_max = 2/sin(√(c/(f·L_cable))) above the cable's half-wave resonance.
  - Assumptions: unshielded, cable ≫ board, about 1 m above ground.
- **emcvisual simplifications** ([RULES.md](https://github.com/tombueng/emcvisual/blob/main/docs/RULES.md) [P-code]):
  - L_p = (4/π²)µ0·l·h/(d1 + d2), V = ωL_p·I, E = 0.365·V (Hockanson/Hubing 1996).
  - I/O coupling: M = µ0/(4π)·ln(1 + 4h²/s²), E = 40·V/Z_ant, Z_ant = 80(N+1) Ω.
- **Ott, via kicad-happy** ([MIT](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md) [P-code]):
  - Differential-mode loop: E = 2.632×10⁻¹⁴·f²·A·I/r.
  - Common-mode cable: E = 1.257×10⁻⁶·f·L·I_CM/r.
  - 2× area → +6 dB; 2× frequency → +12 dB.
- **Cable common-mode current limits:**
  - Ott: <5 µA (Class B) or <15 µA (Class A) for cables ≥1 m; a 0.5 m cable allows 10 µA. Measure with a clamp (F-33-1, 2–250 MHz) and iterate over every cable ([Ott](https://hott.shielddigitaldesign.com/techtips/tips-cm.html) [P]).
  - Hartley: 8–10 µA fails Class B.
- **FCC §15.109** ([CFR](https://www.law.cornell.edu/cfr/text/47/15.109) [P]):
  - Class B at 3 m: 100 / 150 / 200 / 500 µV/m for 30–88 / 88–216 / 216–960 / >960 MHz.
  - Class A at 10 m: 90 / 150 / 210 / 300 µV/m.
- **Consistency checks [HS, D]:**
  - Ott's CM formula at 100 MHz (1 m, 3 m, 150 µV/m) gives about 3.6 µA, consistent with the 5 µA rule.
  - MREMC with 1 mV gives about 61 dBµV/m, roughly 20 dB over Class B. So 1 mV is a hard line.
- **Cavity resonance:** f_mn = (c/2√εr)·√((m/L)² + (n/W)²), independent of plane spacing ([calc](https://learnemc.com/ext/calculators/cavity_resonance/pcb-res.html) [P]).
- **Spread spectrum (Johnson).** It lowers peaks when lines are more than 100 kHz apart, but never use it as the reference for transceivers, PLL CPUs or RF ([P](https://www.sigcon.com/Pubs/edn/clockmod.htm)).

### 1.4 Rise time, critical length, termination, stubs
- **Critical length [CONTESTED per VR]:**
  - Johnson: terminate somewhere between 1/10 and 1/3 of t_r. At ½ t_r, "severe overshoot and ringing". He simulates anything over 1/6 ([P](https://www.sigcon.com/Pubs/news/3_14.htm)).
  - LearnEMC and ADI MT-097: terminate at ≥t_r/2. MT-097's conservative rule is 2 in/ns; a 2" microstrip at Er 4 is about 270 ps ([MT-097](https://www.analog.com/media/en/training-seminars/tutorials/MT-097.pdf)).
  - **Resolution:** t_r/6 means flag for SI review; t_r/2 means terminate.
- **LearnEMC: slow the edge first.**
  - Matched termination is a last resort.
  - Add a series R by default on capacitive loads, and remove it where it is clearly not needed. Use resistors, not ferrites.
  - Transition time ≈20% of the UI: "100 MHz … should never fail at 2 GHz."
  - These are not valid criteria: "terminate beyond λ/4", "series R above 1 V/ns", "Z ≥ Z0/4" ([P](https://learnemc.com/not-so-good-emc-design-guidelines)).
- **Archambeault.** On a 12" trace at 133 MHz, source termination of 10→39 Ω cut harmonic current by 10–20 dB. Choose termination for **minimum current**.
- **Hartley.** SI and EMI problems track rise time, not clock frequency.
- **Stub limits:**
  - Ott: L[in] ≤ t_r[ns].
  - Bogatin, via Telian: the quarter-wave stub length is 3/Gbps in; at 10× margin, **<0.3/Gbps** ([SIJ](https://www.signalintegrityjournal.com/articles/2962-fixing-the-problem-of-stubs) [P; VERIFIED]).
    - 12" at 12 Gb/s with a 0.250" stub transmits <2% at 6 GHz; a 0.025" stub has no visible effect.
    - At 30 Gb/s the limit is about 10 mil. A non-backdrilled via stub is 11 mil (4+3+4 mil). Count the middle pad ring even when backdrilled.
    - "50 mils is too long for even an 8 Gbps stub."
  - f ≈ 1.5/L[in] GHz [S; EDN NOT RETR., arithmetically consistent].
  - TI: <15 mil, otherwise backdrill [VERIFIED].
  - TI Gen5 maximum: about 54 mil (Megtron 6) or 51 mil (FR4).
  - EMA: 20 mil resonates at 8–16 GHz.
  - LPDDR4: ≤20 mil (CA), ≤40 mil (data).
- **Alternatives to backdrill:** route on near-outer layers (L1 to L15 of 16), use sequential lamination, or use blind/buried vias. Decide the stub strategy before the stackup.
- **Pads as stubs.**
  - Telian: enter connector pads opposite the solder leg, otherwise there is about a 50 mil stub. Use SMT connectors at ≥25 Gb/s.
  - TI: enter TH receptacles from the bottom, SMT from the top with no vias [VERIFIED].
- **SerDes test points and stubs: zero** (VR: a P0 "zero", not "minimise").

### 1.5 Crosstalk
- **Johnson** ([P](https://www.sigcon.com/Pubs/news/2_13.htm)):
  - Worst-case NEXT is **K = 1/(1 + (D/H)²)**, where D is the centre-to-centre distance.
  - It scales down by 2T_coupled/t_r when the coupled run is short. D/H = 100 gives 80 dB.
  - Sum the two nearest aggressors plus a little of the next two.
  - Pairs do not cancel aggressor coupling much ([P](https://www.sigcon.com/Pubs/news/3_20.htm)).
  - Extreme isolation: enclose the trace between same-voltage planes with a via row at about ¼" pitch.
- **Ott.** <2% at s = 4h (microstrip) or 2h (stripline); crosstalk ∝ h² [VERIFIED].
- **Bogatin #20/#21.** 2W gives about 2.5% NEXT; FEXT ≈ 0.5%·Len[in]/RT[ns] [S; **NOT RETR.**]. Cross-check: w ≈ 2h, so a 2W gap means D = 6h and K ≈ 2.7%. The rules agree, so encode Johnson's closed form.
- **Johnson broadside data.** In a 20.5 mil cavity, moving from 6 to 4 mil to the plane (traces 7→5 mil) gives 220→143 mV at 13 mil pitch and 38→25 mV at 19 mil pitch, about 35% less.
- **Guard traces [VR CORRECTED].** The source is **Bogatin & Simonovich** ([DesignCon 2013](https://www.signalintegrityjournal.com/ext/resources/article-images-2019/Guard-Traces---Love-Them-or-Leave-Them/4567Guard_Trace_DesignCon-2013-rev14_Final.pdf)); HS's "−60 dB" was a snippet.
  - "−50 dB … perfectly adequate … never a need for a guard trace."
  - Never use a guard in microstrip.
  - In stripline, short the guard's ends with the lowest-L via and match its length to the coupled length: −70 dB vs −50 dB.
  - λ/10 stitching was *tested* and showed "no benefit" in some cases. Use 3-D simulation to quantify.
  - Johnson: "the plane is the … best … guard trace". Guards help only on 2-layer analog boards, grounded at both ends ([P](https://www.sigcon.com/Pubs/news/15_02.htm)).
- **Ground fill on multilayer boards** does nothing and modulates Z0 ([P](https://www.sigcon.com/Pubs/edn/GroundFill.htm)). Floating fill is an Ott red flag.
- **I/O coupling.** Fast nets near I/O nets drive cable common mode (LearnEMC; also a HyperLynx rule).
- **Adjacent signal layers.** Route at 90° ([SPRAAR7J p.14](https://www.ti.com/lit/pdf/spraar7); VR FOUND). Ott pairs H/V layers on one plane. Cross analog and digital at right angles [S].

### Implications for our system
- Build the reference-layer map first. Express edge, void, crosstalk and stitching rules in units of **h**.
- Give each net a t_r (from IBIS, the part family, or an LLM estimate flagged as an assumption). It drives:
  - critical-length flags (t_r/6, t_r/2);
  - the stub limit min(15 mil, 0.3/Gbps);
  - skew budgets;
  - the knee (1/(πt_r) or 0.5/t_r);
  - stitching pitch.
- Rank EMC findings by estimated V_cm or I_CM, not by violation count.
- Never auto-terminate. Recommend slew control or a series R, and flag the net for SI review.
- Spacing: D ≥ H·√(1/K − 1). No guard traces or fill by default.

---

## 2. Stackup selection

**Ott** ([Part 1](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-1.html) [P]):
- Four factors: layer count, plane number and type, layer order, spacing.
- Layer-count drivers: signals and cost, frequency, Class A/B, enclosure, team expertise.
- Five objectives:
  1. every signal layer adjacent to a plane;
  2. signals tight to their planes;
  3. power and ground tightly coupled;
  4. HS signals buried;
  5. multiple grounds.
- 8 layers is the minimum for all five. More is for routing only ("very little EMC advantage" above 8 [VR]).
- 4 layers radiate 15 dB less than 2. Go multilayer above 10–15 MHz.
- Plane capacitance is inadequate below about 500 MHz, so on 4 and 6 layers favour tight signal-to-plane coupling.
- Keep the stack symmetric.

**Hartley** ([P](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley)):
- Never two signal layers on one plane; never stacked power planes without ground.
- 1.6 mm S/P/G/S is bad: planes about 1 mm apart, and every L1→L4 via is a P↔G change. It is OK only with planes ≤ about 10 mil apart.
- S/P/S/S/G/S is "even worse".
- He disowns his older paper.

**Hubing:** no stackup guideline fits more than a small subset of boards. "Two grounds above 25 MHz" is outdated ([P](https://learnemc.com/not-so-good-emc-design-guidelines); VERIFIED).

| L | Stack (Ott [P] + Hartley) | Objectives | Notes |
|---|---|---|---|
| 4 | S/G/P/S, signal–plane <0.010", core >0.040" | 1, 2 | 0.005" spacing gives ≥10 dB less loop radiation. Hartley: avoid at 1.6 mm with fast edges |
| 4 | G/(S+P)/(S+P)/G; power as a grid; grounds stitched at the periphery | 1, 2, 4, 5 | "Best four-layer" [VR FOUND]; pads cut the outer grounds |
| 4 | G/S/S/P | — | Shields inner signals; hard to rework |
| 4 | (S+P)/G/G/(S+P) | 1, 2, 5 | Rework-friendly |
| 4 | S/S/G/S | 1 (L2 only) | Hartley's "worst" |
| 6 | S/S/G/P/S/S | — | "NOT to use" |
| 6 | LF/G/HF/HF/P/LF | 1, 2, 4 | Most common. Ott: OK with careful decoupling. Hartley: "even worse". **Warn, don't reject** |
| 6 | H1/G/V1/H2/P/V2 (5/5/40/5/5 mil) | 1, 2 | Orthogonal pairs share a plane |
| 6 | G/S/G/P/S/G | all | Only two routing layers |
| 8 | LF/P/G/HF/HF/G/P/LF | all | GND–GND via at L4↔L5 changes |
| 8 | G/H1/G/V1/H2/P/V2/G (10/5/5/20/5/5/10) | all | — |
| 8 | H1/G/V1/G/P/H2/G/V2 (6/6/15/6/15/6/6) | 1, 2, 3, 5 | Tight P/G core; Ott's favourite |
| 8 | Six routing layers | — | "Definitely not": use 10 |
| 10 | LF/G/HS/HS/P/G/HS/HS/G\|P/LF | all | Clocks on one HS pair, buses on the other |

**Other stackup inputs:**
- **LearnEMC:**
  - ≥3 power pins on one rail → a plane pair <0.25 mm apart, with HF decaps on that side.
  - Power planes on one layer, non-overlapping (balanced ±12 V excepted), with gap ≥ the plane-to-ground spacing (≥3 mm "Maybe" [VR]) ([P](https://learnemc.com/other-good-emc-design-guidelines)).
- **TI:**
  - At least 6 layers; adjacent signal layers at 90°.
  - HS pairs on outer layers over GND: "**TI does not recommend stripline**".
  - **CONTESTED** against Ott's objective 4. TI's motive is unexplained (perhaps via stubs).
- **Ott's FR-4 rules of thumb:**
  - Microstrip Z0: 60–70 Ω at w/h = 1; 40–50 Ω at w/h = 2.
  - Stripline ≈ 0.6× microstrip; asymmetric stripline ≈ 0.75×.
  - Delay: 150 ps/in (microstrip), 180 ps/in (stripline).
  - Dk 4.0–5.0 (typ. 4.5); Z0 ∝ 1/√εr.
  - u-blox: 50 Ω microstrip width ≈ 2× the dielectric [VR].
- **Fibre weave:** rotate 10–35° or zig-zag; prefer 1080/2116 over 7628 (TI). NXP: route off-axis ([SPRAAR7J p.3–5](https://www.ti.com/lit/pdf/spraar7); [AN10373](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/powerquicc/2284/2/philips_PCIe_pcb_routing_guide.pdf)).
- **Reference stacks:**
  - HDMI retimers: L1–L2 5–10 mil ([TMDS181](https://www.ti.com/lit/ds/symlink/tmds181.pdf)).
  - Espressif: L2 a complete GND.
  - OSH Park 4-layer: FR408HR, L1–L2 7.87 mil, 39 mil core.
  - JLC: Dk 4.5 (2-layer), 4.4 (7628), 4.1 (3313), 4.16 (2116); impedance ±10% (±5% on request); backdrill on 4–32 layers, ≥0.8 mm ([JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities)).
- **Johnson's EMC levers** (preferred to clock modulation): planes, small h, thin packages, slow edges, differential or low-swing clocks.

**Selection algorithm** ([HS] synthesis; no primary scoring function exists):
1. Count routing layers; if ≥6, use 10 layers.
2. Decide whether objective 4 is needed, from edge rate, emission class and enclosure.
3. Enumerate the candidates.
4. Reject: an unreferenced signal layer; two fast layers on one plane; adjacent power planes without a ground.
5. Score: objectives met, minus forced P↔G changes, minus plane separation when ≥3 power pins share a rail.
6. Minimise h, subject to a manufacturable width at Z0. Take the thickness up in the core. Keep it symmetric.
7. Pair orthogonal layers on one plane.
8. Field-solve width and gap per layer, then emit net classes.

### Implications for our system
- **Do the stackup before placement.** It fixes each layer's reference, which vias change reference, the stub lengths, and the width/gap per layer.
- Ship the library and the scorer. Store expert disagreements (Ott vs Hartley; TI vs Ott on stripline) as warnings with a selector: plane separation, edge rate, stub strategy.
- Keep fab stack options as data (not yet researched). Field-solve impedance.

---

## 3. Differential pairs

**Physics (Johnson [P]):**
- **Each leg returns under itself.**
- **Skew → common mode.** V_cm ≈ Δv·Δt/(2t_r), so a 20% skew gives 10% common mode, which dominates radiation and crosstalk ([CMA of Skew](https://www.sigcon.com/Pubs/edn/CMAofSkew.htm)). kicad-happy implements V_CM = V_diff·skew/(2T_rise).
- **0.5 mm spacing gives all the EMI benefit.** In theory it buys about 40 dB of cancellation, but drivers rarely balance better than 1:100 ([P](https://www.sigcon.com/Pubs/edn/ReducingEMI.htm)). LearnEMC: an imbalanced pair radiates like a single-ended line.
- **Corners** ([P](https://www.sigcon.com/Pubs/edn/SkewedLayout.htm)):
  - Each corner adds 2p, 1.65p or 1.57p (square, chamfered, rounded), i.e. 5–6.4 ps at p = 20 mil. **Rounding does not remove skew.**
  - Budget skew to the driver's own skew (≥10% of t_r if unspecified). Examples: 100BASE-TX at 1:1000 → about 0.1"; 2.5 Gb/s → about 20 ps.
  - Place ICs so a pair **exits and enters in the same direction**, so the turns cancel.
- **Serpentines** ([P](https://www.sigcon.com/Pubs/edn/serpentine.htm)):
  - At 8/8/5 mil geometry, NEXT ≈ 6%.
  - A switchback round trip ≫ ⅓ t_r distorts the signal; one ≪ ⅓ t_r advances it by up to 2× NEXT per switchback (4× for a full serpentine).
  - Maximum coupled switchback ≈ 1" per ns of t_r.
  - Match configuration, width, Dk, loading, thresholds and terminations, not just length.
- **XFP differential vias:** an oval antipad with GND vias pinning the planes at each end; no long stubs ([P](https://www.sigcon.com/Pubs/edn/XtkDiffViaGnds.htm)).

| Rule | Value | Source / status |
|---|---|---|
| Pair-to-pair | ≥5W (6 → 30 mil) | TI [VERIFIED] |
| Pair-to-other | **≥30 mil to any signal; ≥50 mil to clocks or periodic signals; no other pair within 30 mil after escape** | [SPRAAR7J p.9–10](https://www.ti.com/lit/pdf/spraar7) [VR addition] |
| NXP pair-to-other | ≥max(20 mil, 4h); 30 mil for higher-voltage or faster aggressors | [AN10373](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/powerquicc/2284/2/philips_PCIe_pcb_routing_guide.pdf) |
| Intra-pair skew | 5 mil (USB3/PCIe/SATA/HDMI); 50 mil (USB2) (AM57xx tables) | VERIFIED+CTX. MIPI CSI uses mode conversion, ≈ UI/50 |
| Compensation | Add length "near the location where the mismatch occurs" | AN10373 [VERIFIED; AN10798 NOT RETR.] |
| Jogs / spread | Jogs ≥15 mil (3W); spread S1 < 2S | **"Amplitude ≥2W" NOT FOUND; the primary rule is a maximum** |
| Uncoupled length | **≤45 mil (1.14 mm)** into a pin or ball; breakout **≤0.25 in** | **CORRECTED** (3.0 mm was a forum value) |
| Vias | Equal on P/N, equally spaced, near the SoC. USB3 ≤2; USB2 ≤4; **PCIe/SATA/HDMI 0 (AM57xx/KeyStone II) vs 2 (AM64x/65x)**; CSI 2 | +CTX / CORRECTED |
| Antipads | Large (30 mil) on all layers; no non-functional pads | VR addition |
| In-line SMDs | ≤0603 (0402 preferred), symmetric. Plane void 100%, ≥2 layers deep; 60% under ESD/EMI pads | VERIFIED |
| Bends | >135° (Rev J; replaces "two 45°"). NXP: ≥135°, ≥20 mil gap, flank segments ≥1.5W, equal left/right bends | VERIFIED (updated) |
| Constant width after escape; ≥1.5W from voids | — | SPRAAR7J |

**KiCad semantics** ([KiCad 9](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html) [P]):
- `skew` is measured against the **longest** net (corrected from "average").
- `within_diff_pairs` applies per pair. `diff_pair_gap` skips fanout. `diff_pair_uncoupled` counts non-parallel or out-of-gap length.
- Pair-to-pair clearance condition: `A.inDiffPair('*') && !AB.isCoupledDiffPair()`.
- kicad-happy's unverified skew limits: USB HS 25 ps, PCIe 5 ps, Ethernet 50 ps, HDMI 20 ps.

### Implications for our system
- skew_max = min(spec or vendor value, 0.1·t_r), tighter for balanced links. Convert using per-layer delay (KiCad 10 profiles; 150/180 ps/in).
- **Running-skew compensation:** insert a tune where |running skew| > 0.2 × budget, not only on end totals.
- Placer cost for pair direction alignment.
- Router:
  - symmetric breakouts;
  - short or uncoupled switchbacks;
  - GND vias at every differential via pair;
  - equal via counts;
  - `diff_pair_uncoupled` from NXP/TI values.

---

## 4. Interface rule packs (vendor-keyed; conflicts flagged)

*[P] unless tagged. TI table values are scoped to the named SoC family [VR].*

### 4.1 USB 2.0 / 3.x / USB4 / Type-C

| Param | Default | Variants / **conflicts** | Check |
|---|---|---|---|
| USB2 Z | 90 Ω ±15% diff, 45 Ω SE ([SLLA414A](https://www.ti.com/lit/pdf/slla414)) | Qualcomm 75–105 Ω; Microchip 90 +5/−10 Ω (Z0 40–55); AN13.10 SE 42–78 Ω | K + solver |
| USB2 intra-pair | ≤1.27 mm (50 mil) ([SPRAAR7J](https://www.ti.com/lit/pdf/spraar7); [AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf)) | SPRAAR7A (2013) 2 mil; TUSB9261/SLLU149E 150 mil; [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb-2dot0-routing-constraints.html) 2 mm | K `skew within_diff_pairs` |
| USB2 length | Warn >150 mm (Microchip, "~6 in"); error >250 mm (Qualcomm) or >304.8 mm (TI J; typ. 101.6 mm) | SPRAAR7A 4 in; SLLU149E ">8 in contact TI". TI loosened sharply between Rev A and Rev J | K `length fromTo` |
| USB2 vias/stubs/TPs | ≤4 / 0 / 0 | Legacy: stub <200 mil | K / G |
| USB2 spacing | ≥30 mil to others, ≥50 mil to clocks | Microchip ≥3·max(W,H) (24 or 66 mil examples); Qualcomm 3W; meanders ≤3X amplitude, ≥5X gap | K |
| USB2 reference | GND ≥5× pair gap each side; parts ≥5× away; no routing under parts ([AN13.10](https://ww1.microchip.com/downloads/en/Appnotes/AN13.10-Application-Note-DS00002972A.pdf)) | — | G |
| USB2 misc | No AC caps, no P/N swap, no branch to 2 connectors; short 1 kΩ stubs; PHY JTAG <6 in; SMPS away; TH entry on the bottom; ≥0.5 mm around TH pins; remove unused pads | — | M/G |
| Shield | **Conflict → ask:** 330 Ω ∥ 0.1 µF (AN26.2); host-only ground, device AC (AN13.10); chassis strap + 10–50 Ω@100 MHz ferrite, optional VBUS 47–1000 Ω (SPRAAR7A) | — | ask |
| USB3 Z | 90 Ω ±15% | AN26.2 85 ±5 Ω; AM57xx 83.7–96.3 Ω; AM65xx 95 Ω ±5%; Qualcomm 70–100 Ω | K + S |
| USB3 intra-pair | 5 mil (SPRAAR7J, AN26.2, SLLU149E; SLLA414A "15 ps/m, TI recommends 5 mils") | TUSB1046 2 mil; TUSB9261 2.5 mil; [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb3dot1-displayport-routing-constraints.html) 5 ps ≈ 0.7 mm (~6× looser; the "relaxed, physics-justified" option [D]) | K |
| USB3 inter-lane / AUX | 70 ps (10 mm) / 50 ps (7 mm) (Qualcomm) | — | K |
| USB3 loss | Connector→PHY: Gen1 ≤5.5 dB@2.5 GHz, Gen2 ≤7 dB@5 GHz (Qualcomm) | Heck: channel −6 to −20 dB, cable ≤7.5 dB | S |
| USB3 vias / layer | ≤2 per trace, plus GND return vias. Qualcomm: inner layers over solid GND, isolated from 2.4 GHz antennas (contrast with TI's "no stripline") | Heck ([DevCon](https://community.infineon.com/gfawx74859/attachments/gfawx74859/usb-superspeed-peripherals/18243/1/2-4_SSUSB_DevCon_DesignGuidelines_Heck.pdf), partly legible): ≈1 in per via; ESD+CMC ≈ −1 in | K + G |
| USB3 length | 88.9 / 139.7 / 101.6 mm (AM57xx / KeyStone / AM65xx); TUSB7340 8 in | Heck: host 2–12 in, device 1–4 in (≤2 in) | K / S |
| USB3 spacing | 5W between pairs and to DP/DM; 30/50 mil (TI) | TUSB1046 3W; Qualcomm 4W (Gen2) / 3W (Gen1) RX–TX; Microchip 5X. Fallback: GND fill, or opposite sides of GND | K |
| USB3 AC cap | 75–265 nF (Gen2), 75–200 nF (Gen1) (Qualcomm); TI controllers 0.1 µF; redrivers 220 nF TX (+330 nF RX); TUSB1046 raised its DP max 200→265 nF | — | M |
| Cap package/void | ≤0402 (0603 absolute; 0201 OK); no C-packs; symmetric; near the connector | **Void conflict:** 100%, ≥2 layers (SLLA414A) vs 60% under ESD (SPRAAR7J) vs 100% under CMC/ESD (Heck) | M/G |
| Chain order | **connector → ESD → CMC → AC cap → PHY** (all sources) | Qualcomm: cap near the source or the connector. TUSB1002A: cap ≥0.25 in from the redriver [S] | G |
| Bends | ≥135°, balanced; one layer; series-only symmetric TPs (TUSB1046) | — | K/G |
| USB4 | [S] only: 85 Ω ±7%, skew <3 mil, ~60 mm; budget 8.5→5.5 dB at 10G (Gen2 8.5 dB ≈ 5 in) | — | low confidence |
| Type-C CC | ≥8 mil (VCONN ≤600 mA); 200–600 pF total (220 pF 0201 X7R example); **no passives** between PD controller and receptacle [S] | TPS65988DK minimum widths (mil): CC 8, VIN 6, GND 10, GPIO 4, cap GND 16 [S] | K/M |
| Type-C protection | TPD6S300A at the connector; protected and unprotected traces apart; straight USB2/SBU with large radii; via *before* the D1/D2 pins; VBIAS 0.1 µF. Mux: connector → AC caps → redriver. No numeric mux distance; CMC-before-mux disputed [S] | — | G |

### 4.2 PCIe Gen2–6

**TI SNLA426 loss budget** ([SNLA426](https://www.ti.com/lit/pdf/snla426)), in dB:

| Item | Gen3 | Gen4 | Gen5 |
|---|---|---|---|
| Package | 3.5 | 5 | 9 |
| 9 in high-loss board | 13 | 14 | 16 |
| CEM connector | 0.5 | 0.5 | 1.5 |
| 4 in add-in card | 6.5 | 8.5 | 9.5 |
| **Total** | **23.5** | **28** | **36** |

Crosstalk allowance: negligible / <2 / 4–5 dB. Gen5 temperature/humidity: 2–3 dB. Eye: 25 / 15±1.5 mV, 0.3 UI.

**Loss per inch at 8 / 16 GHz (dB):**

| Material | 8 GHz | 16 GHz |
|---|---|---|
| Megtron 6 | 0.189 | 0.336 |
| Rogers | 0.251 | 0.411 |
| GETEK | 0.548 | 1.017 |
| Nelco 4000-6 | 0.578 | 1.078 |
| FR4 (Dk 4.4, Df 0.014) | 0.686 | 1.289 |
| Tetra-FR4 | 0.961 | 1.844 |

**Other loss data:**
- [Efinix](https://www.efinixinc.com/docs/an063-high-speed-transceiver-design-guidelines-v1.2.pdf) at 6.25 GHz: ≈0.5 dB/in (Megtron 6), ≈1 dB/in (FR4); RX maximum 25 dB.
- [EMA](https://www.ema-eda.com/wp-content/uploads/2025/10/PCIe-Design-Guide-Part-1.pdf) (EDA reseller, lower authority):
  - Budgets: Gen3 <20 dB@4 GHz; Gen4 <28@8; Gen5 <36@16; Gen6 <32@32 (PAM4).
  - Df: <0.010 / 0.005 / 0.002.
  - "12 in FR4 can exceed Gen5."
- NXP AN10373 (2005): 0.35–0.50 dB/in and 1–5 ps jitter per inch; add-in ≤4 in, system <12 in.
- NXP AN12864: Gen4 1.0–1.2 dB/in [S].

| Param | Default | Variants / **conflicts** | Check |
|---|---|---|---|
| Zdiff | 85 Ω CEM add-in (spec 70–100 Ω) | **TI SoC 100 Ω ±10% (AM57xx/KeyStone), 95 Ω ±5% (AM64x/65x)** [VR]; SLLU149E 100 Ω / 50–55 Ω; REFCLK 100 Ω, ≤200 fs RJ | K + S |
| Intra-pair | ≤5 mil, **additive over segments** | Qualcomm 5 ps (0.7 mm); EMA ±2 mil (Gen4–6) | K per `fromTo` segment |
| Lane-to-lane | Not required (SNLA426 "up to 1 inch", but §13 says <6 in: inconsistent); Qualcomm: no REFCLK/TX/RX matching | SoC groups ≤550 mil, or 6 ns RX / 1.5 ns TX (AM65xx) | On demand only |
| Single-board budget | Gen2 −6 dB@2.5 GHz / 250 mm; Gen3 −10 dB@4 GHz / 300 mm ([Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/PCIe%20layout%20guidelines.html)) | SLLU149E Gen2 20 in FR4; Efinix add-in ≤101.6 mm; TI SoC 4700/5500/4000 mil | S |
| Via cost | ≈2 in per via (Gen2, FR4); layer transitions only at breakout and connectors (Qualcomm) | Heck ≈1 in | Loss score |
| Bends | Round preferred, 45° acceptable, no right angles; SLLU149E prefers 45° (Efinix) | — | K `track_angle` |
| Via geometry | 10/20/40 mil drill/pad/antipad; via-in-pad; NFPs removed | EMA 8–10 / 18–22 / 30–35 mil | G |
| Return vias | ≤50 mil (Gen5) | ≥2 within 100–200 mil (EMA) | G |
| Stubs | <15 mil; Gen5 max ≈51–54 mil | 20 mil resonates at 8–16 GHz | G |
| AC-cap value | **Conflict:** TI 75–220 nF vs Gen3+ 176–265 nF (Qualcomm/Efinix/NXP); Gen2 75–200 (265) nF; SLLU149E 0.1 µF 0402 | **220 nF fits all**; BOM window 176–220 nF | M |
| AC-cap position | **Conflict:** near RX (SNLA426); near TX (SLLU149E); TX side (Efinix); either end (Qualcomm). Agreed: at the connector for add-in/edge cards; never mid-line or staggered; pair caps side by side | "Within N mm of either endpoint" | G |
| Cap package/void | Smallest package (0201 pad 12 mil vs a 5–7 mil trace); void 100%, 2 layers, larger than the pad | — | G |
| Edge/void/spacing | ≥max(5W, 5H) to plane edge; ≥4H to voids; pairs 4–5H apart | Qualcomm 4W; EMA ≥3W (Gen6 4W); Efinix ×5 | K/G |
| Serpentine | Segments ≥max(3W, 3H), at the source end | — | G |
| Edge fingers | No inner copper within 0.381 mm below the fingers; planes ≤2 mm into the footprint (Efinix/CEM 4.0) | — | G |
| Layer | **Conflict:** SPRAAR7J says no stripline; SNLA426/Efinix prefer coupled stripline, or TX/RX on different layers, at Gen4–5 | — | selector |
| Clock buffer (Renesas) | No parts or vias between the lines; 0402/0201; same layer and via count; "1 mm ⇒ 6 ps"; GND via per change; ≥3W (5W optimal); one GND via per decap | — | G |

**Length from budget [D]:** L_max ≈ (budget − allowances) / (dB/in at Nyquist).
- Qualcomm's figures imply ≈0.85 dB/in at 4 GHz and ≈0.6 at 2.5 GHz.
- TI's FR4 figure with a 14 dB Gen4 budget gives about 20 in before vias; realistically 9–12 in.
- **Store budgets and material tables, not mm limits.**

### 4.3 DDR3 / DDR4 / LPDDR4 (controller-keyed)

| Group | TI | Others | Check |
|---|---|---|---|
| DDR3 Z | 50 Ω ±5% SE; 100 Ω ±5% DQS/CK ([SPRABI1D](https://www.ti.com/lit/pdf/sprabi1)) | PolarFire 50/100 Ω | K |
| DDR3 fly-by ADDR/CMD | ±20 mil to CK **at each SDRAM**; equal vias per segment; stubs <80 mil; stub skew ±10 mil; solid GND (or DVDD15) reference on close layers | [Micron](https://cdn.hackaday.io/files/19354828041536/tn4113_ddr3_point_to_point_design.pdf) ±1 mm; Intel ±20 ps [S]; PCBWay ±25 mil, stubs <200 mil [S] | K `skew` + `fromTo` per SDRAM |
| DDR3 CK | ±1 mil per SDRAM; stubs <40 mil; AC VTT termination at the end | — | K |
| DDR3 bytes | DQS ±1 mil; DQ ±10 mil; ≤2 vias, equal; one layer; no mid vias; ODT only; bit swaps OK | Micron ±0.5 mm; Intel ±10 ps, FPGA deskew ≤20 ps [S]; ISSI ±10 ps ≈ ±50 mil [S] | K + G |
| DDR3 spacing | ≥5W c-c including serpentine (4W only ≤1066 MT/s); match stripline-equivalent length | — | K |
| DDR3 termination / VREF / VTT | 39 Ω 1% (39–42) to VTT 0.75 V at the last SDRAM, ≤500 mil. VREF ≥30 mil wide, ≥15 mil gap, top layer, GND-shielded, 0.01 + 0.1 µF per pin, ±1%. VTT regulator near the SDRAMs; VTT island; 0.1 µF per pin + 10–22 µF | — | G |
| DDR3 leveling | ≤2500 ps; DDR3-1333 <2135 (or <1385) / >365 ps at 180 ps/in | — | S |
| DDR4 CK/ADDR | A1+A2 ≤500 ps (skew ≤3); A3 ≤125 ps; AS 5–17 ps (1.3–3); AT ≤75 ps (≤14); CK P/N ≤0.4 ps per segment, ≤0.8 total; CK↔ADDR ≤4 ps per SDRAM; ≤3 vias (Δ ≤1); spacing 4w/3w (2w within ≤500 mil of ends); Rcp Zo ±1 Ω; Rtt Zo ±5 Ω; **no series termination** ([SPRAD06C](https://www.ti.com/lit/pdf/sprad06)) | [PolarFire](https://onlinedocs.microchip.com/oxy/GUID-FF8061A7-7A15-470F-A6F5-E733C24D85F0-en-US-11/GUID-07D00815-AB98-4174-B330-DAD67471AD0C.html) ≤1600 MT/s: **±100 ps**; R_T 30–50 Ω; ODT 80/120/240 Ω | K ps + `fromTo` |
| DDR4 data | BYTE ≤500 ps; DQS P/N ≤0.4 ps; **DQS↔DQ ≤2 ps**; ≤2 vias (Δ0); **no cross-byte matching**; byte swaps OK; bit swaps only without CRC; 1 ps ≈ 5 mil | PolarFire **±25 ps** (training absorbs the rest); Agilex 5 ±3.5 ps, DQS-DQS <1 ps [S] | K |
| DDR4 VREF/VTT | VREFCA 20 mil + 0.1 µF per pin; VTT sub-plane at the bus end; VTT optional with one device, but CK termination still needed | — | G |
| LPDDR4 CA | ≤450 ps (Dk 3.7–3.9); **CK P/N ≤0.75 ps**; ADDR vs CK ±312.5 ps die-to-pin; ≤3 vias; stub ≤20 mil; spacing 5w/3w | — | K + G |
| LPDDR4 data | ≤450 ps; CK−DQS 0–3 tCK; DQS P/N ≤1.5 ps; DQS↔BYTE ≤150 ps; shortest DQ−DQS ≥−49 ps; ≤2 vias; stub ≤40 mil | — | K |
| Policy | **Match to <20% of each limit in the tool; limit as max; confirm with IBIS PVT simulation** | Micron: ≈1% of clock period (±1 mm addr / ±0.5 mm data @ 800 MHz; 6.5 ps/mm; outer layers ~10% faster; ≤20 ps per via; 10 ps = 1.5 mm) | Pack policy |

**Delay conversions differ:** TI SPRAD06C 1 ps = 5 mil; SPRABI1D 180 ps/in; Micron 6.5 ps/mm; Renesas 1 mm = 6 ps; NXP 6 mil/ps for packages [S]. Use the KiCad 10 stackup delay model instead of a constant.

### 4.4 Ethernet 10/100/1000BASE-T and RGMII

| Param | Value | **Conflicts** / notes |
|---|---|---|
| MDI Z | 100 Ω ±10% ([SNLA387](https://www.ti.com/lit/pdf/snla387)) or ±15% ([Pulse](https://www.farnell.com/datasheets/2699973.pdf)); 50 Ω SE | <30 mil edge-to-edge lowers Zdiff by up to 10 Ω (Pulse) |
| Length | TI: total <2 in | [AN2054](https://ww1.microchip.com/downloads/en/Appnotes/00002054A.pdf) and Pulse: <4 in |
| Skew | Intra-pair 20 mil (1G) / 50 mil (10/100) (TI); AN2054 <50 mil intra, <600 mil inter | Johnson: 1:1000 magnetics balance → ≈0.1" |
| Vias | ≤2 per trace, matched; ideally none; no crossovers | — |
| Spacing | Pairs ≥30 mil (TI); TX–RX ≥50 mil, 100 preferred (Pulse); digital ≥300 mil away (Microchip, Pulse) | — |
| **PHY↔magnetics** | **Pulse ≥25 mm "for EMI" vs Microchip <1 in (≤3 in max) vs TI MDI total <2 in**; TI forum PHY→RJ45 ≲3 in [S] | Soft window: target ~25 mm, error >76 mm |
| Magnetics↔RJ45 | <1 in (all sources) | Hard |
| Edge | PHY and TX pairs ≥25 mm from the edge (figure: 1–2 in; silicon 1–4 in from the connector); traces more than their height from the edge (Pulse) | — |
| Voids | Void only under in-line parts: 2 layers, or all layers for automotive, ~20 mil margin; no metal under the magnetics (integrated RJ45 excepted); HV barrier from mid-magnetics to the RJ45 (AN2054) | — |
| Bob Smith | 75 Ω + 1000 pF, ≥2 kV (TI) or 3 kV (Microchip; or 1500 pF/2 kV); ≥50 mil around the cap; not for PoE | — |
| Chassis | ≥20 mil all-layer keep-out bridged by cap + ≥1 MΩ (SNLA387), or 2× 1206 0 Ω swappable at EMC test (AN-1469, DP83867), or 2–3 1206 pads (AN2054); never overlap the planes | — |
| **ESD location** | **TI SNLA387: PHY side of the magnetics, vs generic: at the connector** (SLVA680A) | Pack parameter |
| Misc | 49.9 Ω 1% + 0.1 µF at TD/RD; MII <6 in, matched within 2 in; 25 MHz crystal C_L1 ≈ 2C_L − 7 pF (start at 33 pF); no floating metal; ≥4 layers (6 recommended); bypass pad-to-via <10 mil | — |
| RGMII ([DP83867](https://www.ti.com/lit/ds/symlink/dp83867ir.pdf)) | 50 Ω; skew <11 ps (~60 mil); <2 in recommended, <6 in max | — |

### 4.5 HDMI, DisplayPort, MIPI D-PHY, SATA, UFS

| Interface | Values | Conflicts / notes |
|---|---|---|
| HDMI | Data to 1.7 / 3 / 6 GHz (1.4b / 2.0b / 2.1b); 100 Ω ±15%; **no AC caps**; no swap; intra ≤0.15 Tbit; inter ≤0.20 Tchar (6 Gb/s ≈ 25 ps [D]). TI SoC: 90–110 Ω, ≤4000 mil, ≤5 mil, **0 vias**. Retimers: top layer, controls on the bottom. TPD12S016: ESD at the connector, no vias to it, no 90° | ADV3003 inter ≤0.05 in [S]; Intel ±10%, ≤2 vias [S] |
| DisplayPort | 100 Ω ±10%; AC caps; intra ≤20 ps (TI) | Qualcomm 5 / 70 / 50 ps (intra / inter / AUX). Caps 75–200 nF (DP 1.2) vs 75–265 nF (newer) |
| D-PHY ([Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/mipi-csi-d-phy-routing-constraints-up-to-2dot5-Gbps.html)) | 70–100 Ω, 36–52 Ω SE; intra 0.7 mm, inter 1.4 mm; spacing 2.5W others / 1W intra / 1–1.5W inter | TI AM62x: ≤10 in; 85–115 Ω; **loosely coupled** (LP mode); intra ≈ UI/50; lane ≤40 ps; ≤2 vias |
| D-PHY length vs rate | Rates 0.5 / 0.75 / 1.0 / 1.5 / 2.1 / 2.5 Gb/s → IL −2.1 / −2.3 / −2.3 / −2.5 / −3.5 / −6.5 dB. Max trace, better cable: 260 / 210 / 200 / 145 / 170 / 210 mm. Worse cable: 190 / 155 / 125 / 60 / 90 / 150 mm | Non-monotonic because of the assumed flex length → **`cable_il_db` input** |
| SATA | 100 Ω ±15%; ≤2.5 mil; caps ≤0402 at the connector; TX↔RX 5W; **P/N swap allowed** (TUSB9261) | SPRAAR7J: 85–115 Ω, ≤3500/5500 mil, ≤5 mil, 0 vias. Caps 0.3–12 nF (typ. 10) [S]. LattePanda: no inversion; caps ≤10 mm [S] → controller-dependent |
| UFS (Qualcomm) | G3: −6 dB@3 GHz, 25/75/150 mm, 75–105 Ω. G4: −1.3/−5.0 dB@2.9/5.8 GHz, ≤70 mm, 70–110 Ω. Intra 5 ps; lane–lane 30 ps (4.2 mm); RX–TX 1.5–3W | — |

UI budgets are stored as formulas, resolved to ps at the configured rate, then to mm via per-layer delay.

### 4.6 CAN, RS-485, I2C, SD/SDIO, SPI/QSPI, slow clocks

| Bus | Rules |
|---|---|
| CAN ([SLLA270](https://www.ti.com/lit/pdf/slla270), [TCAN1042H](https://www.ti.com/lit/ds/symlink/tcan1042h.pdf)) | **Termination:** 120 Ω at the two ends only, or split 2×60 Ω ±1% + 4.7 nF; it must survive node removal. **Topology:** 40 m@1 Mb/s, ≤30 nodes, stub ≤0.3 m; 100/200/500/1000 m at 0.5/0.25/0.1/0.05 Mb/s; above 100 m, rate × length ≤50; stub ≤⅓ critical length (50 ns → 1.67 m; 160 ns → ~5.3 m). **Protection:** TVS, filter and CMC at the connector, *in the signal path*; ≥2 vias on protection GND |
| RS-485 ([SLLA272D](https://www.ti.com/lit/pdf/slla272)) | 120 Ω at each end (2×60 Ω low-pass when noisy); stub L ≤ t_r·v·c/10 (1 Mb/s → 7 ft; 250 kb/s → 19 ft; 200 kb/s → 38 ft); failsafe 2×523 Ω @5 V; 32 UL; length × rate <10⁷; lines close and equidistant |
| I2C ([SLVA689A](https://www.ti.com/lit/pdf/slva689)) | t_r ≤1000/300/120 ns; C_b ≤400/400/550 pF (Sm/Fm/Fm+); R_P ∈ [(VCC − 0.4)/3 mA, t_r/(0.8473·C_b)]. Fully automatable from stackup pF/mm + pins |
| SD ([Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/SDC2%20external%20SD%20card%20routing%20constraints.html)) | 50/100 MHz: 10 pF, <150 mm, CLK↔data 6 mm. 208 MHz: 5 pF, <50 mm, 2 mm. Spacing 1.5W; CLK series 18–27 Ω at the source |
| SDIO ([Espressif](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html)) | ±50 mil to CLK; ≤2000 mil; GND around CLK; 50 Ω ±10% |
| QSPI 133 MHz (Infineon AN240090) | ±30 / ±200 / ±1500 mil [S, first pass] |
| Slow clock (Qualcomm) | Star branches Δ <30 mm; daisy stubs <7 mm |

On-PCB CAN/RS-485 stubs matter only for daisy-chained connectors. The useful checks are "termination only at end nodes" and "protection in the signal path". No primary source gives a TVS distance.

### 4.7 Clocks and crystals

| ID | Value | Source |
|---|---|---|
| XTAL-DMAX | ≤12 mm (½ in) to the oscillator pins; same side; caps adjacent | [Microchip dsPIC33AK](https://onlinedocs.microchip.com/oxy/GUID-E48B4A26-F201-4F0A-BCBA-16461582816A-en-US-4/GUID-AA04B64F-3C38-4E1C-8B51-49DE3CFE2419.html) |
| XTAL-DMIN (vendor-specific) | ≥2.7 mm (ESP32) / ≥2.0 mm (ESP32-S3) from the clock pin; dense GND vias; **no vias on clock traces** [VR] | [Espressif](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html) |
| XTAL-PAR | XIN–GND 1 pF, XOUT–GND 2 pF, XIN–XOUT 0.5 pF (AVR186); stray 2–5 pF (AN826); C_SHUNT 4.5 pF (TUSB9261); ~3.5 pF (AN-1469); 2–3 + 7 pF = 9 pF (SWRA495L) | [AVR186](https://www.insidegadgets.com/wp-content/uploads/2013/02/Best-Practices-for-the-PCB-layout-of-oscillators.pdf); [AN826](https://ww1.microchip.com/downloads/en/AppNotes/00826a.pdf) |
| XTAL-SENS | 0.175 pF × 45 ppm/pF ≈ 7.8 ppm; LSE C_L ≥6 pF (7 typical); gain margin >5; PC13 toggling shifts LSE; Cs = pin + PCB. 802.15.4 carrier tolerance ±40 ppm (SWRA495L) | [ST AN2867](https://ecsxtal.com/store/pdf/stm32-microcontroller-application-note.pdf) [VERIFIED; no mm] |
| XTAL-GUARD | Grounded ring or pour; no foreign nets inside or on the adjacent layer; tie to MCU GND; tie broken guards to a mirrored layer; nothing under the crystal on 2-layer boards; Espressif top-layer keep-out | Microchip; AN2867 ("essential"); SLAA322D; Espressif |
| XTAL-CAP | XIN cap first; C0G; short symmetric loop with cap grounds together; never route GND between the caps; keep cap grounds away from USB/RS-232/LIN/PWM/power returns; series R at the chip side | AVR186; [SLAA322D](https://www.ti.com/lit/pdf/slaa322); Espressif |
| XTAL-SEP/TP/MAG | XIN/XOUT apart; no test points; conformal coat; no magnetics nearby; no HS traces near crystals, oscillators, SMPS, magnetics or mounting holes | AN2867; Espressif; SPRAAR7J |
| **XTAL-CAN** | **Conflict:** ST: don't tie the can to oscillator GND. TI/AVR: tie it to ground. TUSB9261: VSSOSC off the plane | Vendor switch |
| **Copper under** | **Conflict:** solid ground (most sources, plus Nordic) vs cut planes (TI CDCE925 [S]) → ground for an MCU Pierce; cut only per the datasheet | — |
| Other | C-shaped GND ring around clock vias (Qualcomm); driver beside its oscillator (LearnEMC); emcvisual: crystal ≥5 mm from edge, ≥10 mm from cable connectors | — |

No primary source gives a crystal-to-switch-node distance. [IF]'s 3 mm is [D]; ≤5 mm is a heuristic [VR].

### 4.8 Adjacent packs in IF (SMPS §8, fab §10; overlap the power/DFM digest)

**SMPS:**
- **MPS** ([AN065](https://media.monolithicpower.com/document/PCB_Layout_Design_Guidelines_for_NB67xSeries.pdf)):
  - **Cin <2 mm**, the only numeric primary value; VCC cap <2 mm.
  - Vias: AGND–PGND ≥2; 4/8 vias; 10/20 mil vias; >20 vias between the input caps.
  - FB divider at the pin with no vias; Inner1 = PGND.
- **Rohm** ([60AN066E](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf)):
  - CBYPASS 0.1–0.47 µF on top; bulk ≈2 cm away; "even 1 mm" matters.
  - **Cin–Cout grounds 1–2 cm apart.**
  - 0.3 mm thermal vias at 1.2 mm pitch; >1 mm/A (1 oz) or >0.7 mm/A (2 oz).
  - Via L ≈ (h/5)(ln(4h/d)+1) nH.
- **Loop anchors:**
  - [SNVA803](https://www.ti.com/lit/pdf/snva803): 20 mm² lateral >1 nH; 2 mm² vertical <0.5 nH, ≈4 V less overshoot.
  - [EPC](https://epc-co.com/epc/documents/papers/Optimizing%20PCB%20Layout%20with%20eGaN%20FETs.pdf): 0.4→2.9 nH costs >4%; overshoot 100% → 30% going from 1.6 to 0.4 nH.
  - [SLYT682](https://www.ti.com/lit/pdf/slyt682): 5 A/ns × 2 nH = 10 V; 5 mil L2; keep top copper out from under the inductor.
  - AN-139: 187→13 nH.
- **Other TI:** SLYT614 order Cin → L → Cout, 1 via/A. LM10504 SW ≤100 mil. SLVA773 FB not parallel to SW. LM5163: shield FB when R_FB >100 kΩ [S].
- **Conflicts:** Cin/Cout grounds (Rohm vs TI/MPS); copper under the inductor (Rohm vs TI) [VR CONTESTED].
- **Loop tiers [D]:** ≤2 / ≤10 [S] / >20 mm². These are soft, since no primary pass/fail exists.

**Fab:**

| Parameter | JLC 2L (rec/abs) | JLC ML | PCBWay | OSH Park 2L/4L |
|---|---|---|---|---|
| Trace/space (1 oz) | 0.10/0.10 | 0.09/0.09 (3 mil BGA) | 0.10/0.10 | 0.152/0.127 |
| Drill | 0.2/0.15 | same | 0.15 (≥0.2 no surcharge) | 0.254 |
| Annular ring | 0.25/0.18 | 0.20/0.15 | 0.15 | 0.127/0.102 |
| Copper to edge | 0.2 routed, **0.4 V-cut** [VR] | same | 0.20–0.25 | 0.381 |
| Silk | 0.15 line, **1.0 mm text** [VR CORRECTED], 0.15 to pad | same | 0.15 / 0.8 | 0.127 |

**Further fab and mounting data:**
- **JLC** ([JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities)):
  - via 0.15/0.25 mm;
  - hole-to-hole 0.2 (via) / 0.45 (pad);
  - PTH-to-track 0.28 (0.35 recommended);
  - mask bridge 0.10/0.13;
  - panels: 5 mm rails, 2 mm tooling holes, 1 mm fiducials at 3.85 mm;
  - pitch 0.35/0.40 mm.
- **JLC outline:**
  - routed tolerance ±0.2 mm;
  - V-cut ±0.4 mm, 25°, ≥2 mm apart (3 mm recommended);
  - mouse bites 1.6 or 2 mm;
  - castellations ≥0.5 mm, 1 mm from the edge;
  - impedance ±10%.
- **PCBWay:**
  - hole tolerance ±0.08 mm (PTH) / ±0.05 mm (NPTH);
  - half-holes ≥0.4 mm;
  - panel spacing 1.6 mm.
- **Eurocircuits:** IPI = IAR + 0.075 (≥0.2 mm); NPTH ring ≥0.30 mm.
- **Assembly spacing (secondary sources only):**
  - Cadence: 0.25–0.3 mm side-to-side, 0.5–1 mm to the edge [S].
  - TI: ≥0.508 mm between lands [S].
  - Courtyards: 0.25 mm (IPC-7351 B), 1.0 mm for BGAs, ~1.5 mm for BGA rework [S].
  - Panels: V-score ≥2 mm; MLCCs 3–5 mm from V-cuts.
  - JLC: 0.2/0.4 mm component-to-outline [S].
- **Mounting holes:**
  - RP2040: "NPTH FD2.75 SM3.15 **KO6mm**" ([RPi](https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf)); other Pi boards KO 6.2 mm.
  - M3 holes 3.2/3.4/3.6 mm [S]. No HS traces near holes (TI).
  - Keep-out Ø = max(head + 2×0.5 mm, vendor example).
- **Precedence:** fab packs set `min` only (precedence 10); interface packs never relax them.

### 4.9 Vendor-spread summary

| Quantity | Tightest | Loosest | Ratio |
|---|---|---|---|
| USB3 intra-pair | 2 mil (TUSB1046) | 0.7 mm (Qualcomm) | ~14× |
| USB2 intra-pair | 2 mil (SPRAAR7A 2013) | 150 mil (TUSB9261) | 75× (historic) |
| DDR4 DQ↔DQS | 2 ps (TI) | 25 ps (PolarFire) | 12.5× |
| DDR4 ADDR↔CK | 4 ps (TI) | 100 ps (PolarFire) | 25× |
| Ethernet PHY↔magnetics | <1 in (Microchip) | ≥25 mm (Pulse) | opposite directions |
| PCIe AC cap | 75–220 nF (TI) | 176–265 nF (Qualcomm) | 220 nF fits both |

### Implications for our system
- **Vendor profile per pack.** When the vendor is unknown, use the tightest [P] value plus an `info` finding.
- **Store physics budgets, not mm:** dB budgets, material tables, per-via (≈1–2 in) and ESD+CMC (≈1 in) penalties, UI formulas, cable IL. Compute L_max per stackup.
- **Delay packs** emit ps rules with `opt` = 20% of the limit and `max` = the limit. DDR fly-by needs one `fromTo` rule per SDRAM per group.
- **Placement intents** come from the packs: chain order, distance windows (crystal annulus, Ethernet ~25 mm), end-node termination, AC cap at either endpoint.

---

## 5. EMC placement: connector zoning, protection, stitching, edges

**Zoning** (LearnEMC [P]; VR VERIFIED, with numeric defaults):
- Cabled connectors on **one edge or corner**.
- **No HS circuitry between connectors** (Guideline #3, "one of the most common problems"), or else a chassis bonded at both connectors.
- I/O devices within **~2 cm** of their connector; one connector per device's off-board links.
- Non-I/O parts **≥2 cm** away ("not necessarily the best advice in every situation").
- No unrelated traces between a connector and its device; no HF under I/O parts.
- Clock driver beside its oscillator; exclusive communicators together.
- Few vias on HF nets; tie unused inputs.
- **Worst guideline:** "group by type, HS farthest from the connector". Instead, put each connector's talkers nearest it.

**I/O nets and filters** (LearnEMC [P]):
- Every I/O net ends in a series or filter part at the connector. An IC driving a cable directly must inject ≤ about 1 mV of common mode.
- Filters: low-parasitic mounting, no ringing higher-order designs. CMCs only on **balanced** pairs. **Never a ferrite on ground.**
- Protection grounding: IC protection to the IC's ground; board protection to the EMC ground.
- ESD current goes to a metal enclosure without crossing the board. With plastic enclosures, check seam arc paths, and slow high-impedance inputs with resistors.
- Treat all pins of a fast IC as HF sources (DRAM supply pins exceed signal pins).

**TVS topology** ([SLVA680A](https://www.ti.com/lit/pdf/slva680) [P]; VR: topology VERIFIED, mm distance NOT FOUND):
- Place the TVS "as near to the connector as design rules allow", and the IC "much further from the TVS than the TVS is to the connector".
- No stubs and no via between the source and the TVS. If a via is needed, go source → TVS → via (Case 1); avoid branching to the IC before the via (Case 2).
- **0.25 nH adds 10 V** at 8 kV (dI/dt = 4×10¹⁰ A/s).
- A 90° corner develops ≥7 kV and arcs below a **2.6 mm** radius. Use curves (≤45° at most). The region is a keep-out for unprotected traces.
- TVS GND: one via **immediately adjacent** to the pin, into a same-layer plane coupled to an adjacent plane (example: 4 stitching vias + a chassis screw).
- Example BGA-TVS via: 0.254 mm pad, 0.152 mm drill, filled and capped, 0.1 mm clearance. Make GND vias as large as possible.
- The 5–10 mm figure is a blog heuristic → soft.
- emcvisual: flag a diode nearer the IC than the connector, or one with no GND pour or via within 2 mm.

**CMCs and filters:**
- TPS case: a choke >30 mm away failed CISPR 25; within **5 mm** of the DC connector it passed ([TPS](https://tps-elektronik.com/en/case-studies/how-to-pass-automotive-conducted-emissions-cispr-25-class-5-with-tps-split-ground-plane-and-common-mode-choke-placement-emc-layout-guidelines-for-automotive-dc-dc-converters/); VERIFIED case study).
- TI: AC caps on the protected side of the CMF; 0402 0 Ω no-stuff alternative to the CMF.
- emcvisual: flag filter parts >10 mm from the pin.

**Edges** (VR closed this gap):
- TI: **≥90 mil** from the reference-plane edge.
- LearnEMC: **≥2X** from the board edge (X = trace-to-return height).
- u-blox: **>3W** from the GND edge.
- Other values:
  - TI Gen5: 5·max(W, H).
  - Microchip: SS ≥5W from plane edges and splits; narrow floods via'd at corners and ends.
  - Pulse: more than the trace height; Ethernet ≥25 mm.
  - [HS]: centreline ≥ w/2 + 3h.
- Checker thresholds: kicad-happy < h; EMI Guardian 1 mm; emcvisual <3h (≥1 mm) over ≥3 mm.
- A copper guard band along the edge best suppressed edge-driven common mode [S].
- Plane edges are zone-boundary checks; `edge_clearance` covers only Edge.Cuts.

**Stitching** (CONTESTED):
- Ott stitches the G/S/S/G periphery as a Faraday cage. LearnEMC: perimeter vias every 2 cm are "not-so-good". They are usually unnecessary, and a perimeter-only ring "will create a resonant cavity", so distribute instead.
- **No primary λ/20 or 3–5 mm pitch exists.** λ/20 is Ott's *aperture* red flag (6" at 100 MHz).
- TPS: split boundaries every **10–15 mm**. 40–50 mm failed and 12 mm fixed it ("above 100 MHz the slot … acts as an effective antenna"; medium authority, soft).
- Johnson: a ¼" via row; 10:1 via ratio.
- u-blox: a stitched GND ring at the edge, with power planes kept back.
- KiCad master stitch default: max(2 mm, 2× via).

**Grounding and chassis:**
- **One ground.** Hubing 2019: "more than one ground" is MOST EGREGIOUS ([slides](https://r6.ieee.org/scv-emcs/wp-content/uploads/sites/111/022019ToddHubing.pdf)). Clearing ground under magnetics, inverters or HV is fine; gapping it is not.
- **Chassis:** an overlapping chassis layer bonded with multiple SMT caps, plus one LF tie. Never a single point at the I/O by default, and never at the oscillator. "Bond (at RF) everything that leaves the board"; near metal, "Connect to it!"
- **Mixed signal (Ott):** one partitioned plane with routing discipline on all layers.
  - LSB at 1 V: 8-bit 4 mV; 10-bit 1 mV; 12-bit 240 µV; 14-bit 60 µV; 16-bit 15 µV.
  - At ≥14 bits: isolated regions joined under each ADC; no trace crosses the slots on any layer.
  - Test: 0 Ω jumpers every ½", compared split vs joined.
- **Power stages (LearnEMC):**
  - Keep switch-node area minimal and away from conductors that could carry the noise off; watch the switching-loop magnetic coupling.
  - Modern DC-DC converters should switch in the MHz range, with no isolated power grounds.
  - Transitions longer than ~1% of the switching period cost efficiency [VR].
- **Deliberate splits only:**
  - MT-031: >300 mV between planes risks latch-up.
  - DA9080 mandates GND cuts between bucks → allow a datasheet override [VR].

**Pre-compliance:**
- **LearnEMC 10-step review**, held before layout and again at the first draft:
  1. ground and I/O;
  2. plane extent;
  3. remove ground traces and fills;
  4. power on a <0.25 mm pair;
  5. I/O nets;
  6. filters;
  7. transition times;
  8. critical parts (op-amp loops over the plane, PLL ferrites, no ferrite on ground);
  9. inverters;
  10. each test's current path (CE/RE/BCI/RI/EFT/ESD).
- Leave **optional filter, TVS and shield footprints**.
- "Blindly adhering" to rule lists fails. Identify sources, victims and paths ([LearnEMC](https://learnemc.com/effective-application-of-emc-design-guidelines)).
- **Johnson:** simulators can't handle real EMI; tools should be "more like expert systems". "2× last year's design needs another 6 dB." Scan early.
- **Ott:** clamp every cable.
- **Hubing's seven errors:**
  1. blind guidelines;
  2. uncontrolled transitions;
  3. not following currents;
  4. missing critical traces;
  5. multiple grounds;
  6. bad decoupling;
  7. bypassed filters.
- **Ott's red flags** ([P](https://hott.shielddigitaldesign.com/techtips/red_flags.html)):
  - edges <10% of period;
  - apertures >λ/20;
  - split grounds;
  - traces over slots;
  - pigtails;
  - non-contacting backshells;
  - painted seams;
  - unreferenced signal layers;
  - multi-value parallel decaps;
  - ungrounded fill or thieving;
  - unfiltered unshielded cables;
  - single-point chassis bonds.
  
  His satirical "maximize emission" list, inverted, is worth 20–30 dB ([P](https://hott.shielddigitaldesign.com/techtips/maxemission.html)).
- **emcvisual placement thresholds** [P-code]:
  - crystal ≥5 mm from the edge and ≥10 mm from connectors;
  - inductor ≥3 mm from the edge and ≥10 mm from connectors;
  - switch node <100 mm² (<40 mm² near an edge or connector);
  - hot loop flagged at 30–40 mm².

**Placement priority** ([HS] §8):
1. Mechanicals, connector cluster, I/O zone.
2. Protection, filters, CMC, magnetics and chassis bond at the pins.
3. Interface ICs ≤2 cm away, with a clear corridor.
4. SoC, fly-by DRAM and SerDes: short, uncrossed, direction-aligned links, never between connectors.
5. Clocks next to their consumer, away from I/O and edges.
6. Functional partition over one plane; power away from I/O.
7. In-line SI parts (series R at the driver, AC caps), then decaps.

Steps 1–3 are hard (anchor-relative). Steps 4–6 are soft costs with no published weights.

### Implications for our system
- **Placer costs:** MREMC V_cm between connectors; I/O intrusion; fast-net length and crossings; pair direction alignment; crystal, inductor and SW-node distance to edges and connectors.
- **TVS/CMC as comparative constraints:** d(TVS, connector) < d(TVS, IC); zero vias before the TVS; GND via at the pad.
- **Edges, per layer:** ≥2h to the board edge (`edge_clearance`), and ≥90 mil or w/2 + 3h to plane edges (geometric).
- **Stitching:** a single "largest unstitched region" metric sidesteps the perimeter debate.
- **Optional footprints** (CMF 0 Ω, TVS, shield pads, chassis R/C) when compliance is uncertain.

---

## 6. Myths and context-dependent rules (negative rules carrying the physics replacement)

| Slogan | Verdict | Status |
|---|---|---|
| 90° corners | Negligible to ~2 Gb/s (≈1 ps, 0.012 pF, ≈0.3% at 100 ps). Rounding removes 21% of the copper, but 70–90% would be needed. They matter around 10 Gb/s and for pair skew. Myth from the MECL handbook (1971); 3 Ω at ~80 GHz; a 5 mil corner = 8.5 fF, no impact below ~70 GHz | VERIFIED+CTX. **Exceptions:** ESD paths ≤45° (2.6 mm arc); RF arcs or 135° ([Johnson](https://www.sigcon.com/Pubs/edn/bigbadbend.htm); [Altium](https://resources.altium.com/p/slaying-900-right-angle-bend-dragon)) |
| 20-H | Shim & Hubing: "slightly higher" far field (3.6 dB NOT RETR.). LearnEMC: helps only when power is sandwiched between grounds; 2–3H is enough. **Montrose 2005 FDTD: "fact, not fiction"; 10-H may suffice; only on high-density multi-plane boards; components negate it** | **CONTESTED → selector** ([Montrose](https://courseware.zcu.cz/CoursewarePortlets2/DownloadDokumentu?id=186283)) |
| Split A/D ground | Only for <100 kHz at ~1000:1 sensitivity, and better as a separate-layer return | +CTX (≥14-bit exception) |
| I/O ground island, single tie | "One of the worst" | LearnEMC; Ott |
| Group by type, HS far from the connector | "More crazy layouts than any other" | LearnEMC |
| 3W rule | A proxy for D/H; use K | Johnson; Ott |
| Guard traces | Stripline only, end-shorted, length-matched | **CORRECTED** |
| Multilayer ground fill | No function; perturbs Z0; floating fill is a red flag | Johnson; Ott |
| Perimeter vias every 2 cm | Usually unneeded; can form a cavity → distribute | CONTESTED (Ott's G/S/S/G) |
| Two grounds above 25 MHz | Outdated | VERIFIED |
| λ/4 termination; series R above 1 V/ns; Z ≥ Z0/4 | Not criteria; compare delay to t_r | LearnEMC |
| Single-point LF / multipoint HF | Misused. At LF limit the options; at HF give one good path | LearnEMC |
| Minimise all HS lengths | Not an EMC fix ("control loop areas"); guideline-followers do worse than designers with no guidance | VERIFIED |
| Rely on slow logic | Parts speed up over a product's life; use slew control | VERIFIED |
| Ferrite on ground | Never | LearnEMC |
| 0.1 µF ≤15 MHz / 0.01 µF above; 1 ground per 8 lines | Too narrow | VERIFIED |
| Decaps across a plane gap | "Don't gap the ground plane!" | LearnEMC |
| Daughterboards grounded to chassis | Returns belong on connector pins | LearnEMC |
| Rounded corners fix pair skew | No (1.57p–2p) | Johnson |
| Tighter coupling always reduces EMI | Not below ~0.5 mm | Johnson |
| Follow as many guidelines as possible | 90% compliance can be worse than following 1–2 | LearnEMC |
| More anti-rules | "Power traces ≥3× signal width"; ground islands under ICs; "daisy chain, no stubs" ("sometimes"); "ground E-shields at ≥2 points" ("terrible") | [VR] |

### Implications for our system
- Each myth is a **negative rule** that blocks the slogan and points to its replacement physics check.
- The corner rule applies only to net classes `ESD_UNPROTECTED` and `RF50`.

---

## 7. Hard vs soft vs explicit-selection rules ([VR] §3)

| Class | Rules | Encoding |
|---|---|---|
| **Hard: fab/assembly** | Fab absolute minimums (router targets the recommended values); courtyard non-overlap; IPC-2221B floor; JLC silk 1.0/0.15 mm | Board setup + `.kicad_dru` |
| **Hard: topology** (all primary sources agree) | No split or void crossing; ≥1.5W from voids (except voided SMD pads); crossings over the bridge; connector→TVS→IC with no stub, no via before the TVS, GND via at its pad; 0 TPs/stubs on SerDes. Power/RF: CIN on the IC layer with 0 hot-loop vias; FB from the COUT pad; single "mandatory" AGND–PGND tie; shunt cap via the named VSS pin; antenna keep-out polygon; no digital under RF; AGND+DGND to the analog plane | G-checker → reject |
| **Hard within scope** | Pair skew, via count, 30/50 mil keep-outs, via stub min(15 mil, 0.3/Gbps) | Only when the interface and rate are known; `source_scope` |
| **Soft, strong** | Return via ≤200 mil hard max, "closer is better" as the objective; ≥90 mil from plane edge / ≥2h from board edge; one-edge connectors; I/O ≤2 cm, non-I/O ≥2 cm. Power: L2 ≤0.13 mm; 1 via/A; C_boot ≥10·Cg; bead ≤20% of rated current; EP vias 0.3 mm at 1.0–1.2 mm | High-weight costs; warnings with the quote |
| **Soft, weak** | TVS ≤5–10 mm; CMC ≤5 mm; crystal ≤5 mm; CIN ≤0.5–1 mm (MPS ≤2); FB ≤2–3 mm; RF↔SMPS 20 mm; stitching λ/20, 3–5 mm, or 2 mm near SerDes; **2W/3W/5W (compute crosstalk in h instead)**; 2 cm²/W | Rank objectives; never DRC |
| **Context switch** | 20-H; copper under inductors; CIN/COUT grounds; **microstrip vs stripline**; tenting; guard traces; "smallest cap closest"; perimeter stitching; PMIC ground cuts; **termination at t_r/2 vs t_r/6** | Store both + selector (power, layers, rate, fab, datasheet); ask; log |
| **Myth exceptions** | 90° corners on ESD/RF nets | Net-class scoped |

**Recalibrations:**
- TL-5 (SerDes test points) → hard.
- EMI-7: mm distance soft; topology stays P0.
- EMI-6: pitch soft; P0 = "no crossing without a bridge or stitch".
- RF-05 split into a hard PCB keep-out plus an enclosure clearance for the mechanical checklist (ESP32: 15 mm).

**Schema additions:** `source_scope`; `statement_strength` (mandatory / must / should / as close as possible / good guideline); `contested_by`.

**Where the LLM adds value:** turning relative wording into **comparative constraints** (ratios, rank orders) instead of invented mm values.

### Implications for our system
- Three output tiers: DRC errors (hard); scored warnings (soft); user decisions (context switches, logged with rationale).
- [D] heuristics stay warnings until calibrated against vendor evaluation boards.

---

## 8. Encodability: KiCad native vs custom geometric checkers vs simulation

**KiCad 9/10 native constraints:** `track_width`, `clearance`, `diff_pair_gap`, `diff_pair_uncoupled`, `skew` (vs the longest net; `within_diff_pairs`), `length` (also the tuner target), `via_count`, `edge_clearance`, `track_angle`, `track_segment_length`, `assertion`, `hole_size`, `annular_width`, `hole_to_hole`, `silk_clearance`, `courtyard_clearance`, `text_height`/`text_thickness`, `physical_clearance`, `via_diameter`, `disallow`.

**Conditions:** `hasNetclass`, `inDiffPair`, `isCoupledDiffPair`, `intersectsArea`, `intersectsCourtyard`, `memberOfSheet(OrChildren)` (9.0.2). KiCad 10 adds **`fromTo('U1-A*','U2-B*')`**.

**KiCad 10 time domain** ([docs](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html)):
- Delay = Σ length × per-layer delay + via delay (stackup height × via unit delay, with per-layer-pair overrides) + pad-to-die.
- Profiles in ps; recommended for DDR/PCIe/USB even on one layer.
- ps and mm cannot be mixed in one constraint.
- Backdrill on vias and pads, from one or both sides, with a "must-cut" layer.

**KiCad master** ([keywords](https://gitlab.com/kicad/code/kicad/-/raw/master/common/drc_rules.keywords) [P-code]) adds `return_path`, `stub_length`, `net_chain_length`, `hole_aspect_ratio`, `microvia_stack_depth`, `net`.
- **`return_path (layer "B.Cu") (net "GND")`** has four steps:
  1. Union the zone fills on the named layer.
  2. Subtract that union from each net-chain track polygon.
  3. Report any remainder as unreferenced.
  4. Union-find to merge flags.
  
  It covers one layer only. It does not check vias, detours, edges or reference changes.
- **Net chains** bridge series parts; the topology gives the trunk plus each stub's branch point, length and delay.
- **`PCB_VIA_STITCH`:** STITCH/GUARD modes; PLAIN/STAGGERED/POISSON layouts; pitch max(2 mm, 2× via). Exposed via IPC (`ViaStitchGuardSettings`), with a DRC check for stitch overlap.
- Syntax may change before KiCad 11. Whether `A.NetChain` conditions will exist is unknown.

**IPC API (kipy, MIT):** `get_stackup`, `get_zones`, `refill_zones`, `get_pad_shapes_as_polygons`, `hit_test`, `Zone.filled_polygons`.
- SWIG does not expose the stackup → parse `.kicad_pcb`.
- KiCad 10 IPC cannot create persistent custom DRC markers → use an HTML/JSON overlay plus selection and zoom.

### Custom checker specifications ([HS] §11 + [IF])

**A. Reference map**
1. Read the stackup.
2. For each signal layer, record its neighbours, h_up/h_down, and whether each neighbour is filled with GND or a declared reference net.
3. Take the nearer filled layer as the reference. For stripline keep both (≈75% returns on the nearer).
4. Refill zones first, and lint Ott's objective 1.

**B. Return continuity**
- Fast path: master `return_path`.
- Full path:
  1. Sample against a net-labelled raster or polygons.
  2. Find the geodesic detour, entry to exit (A* on the raster, or a visibility graph).
  3. Classify as VOID, ISLAND or SPLIT.
- **Merge antipads into voids first.**
- Buffer by 1.5W or w/2 + 3h. Severity scales with t_r and detour/h.

**C. Reference change**
1. At each via or PTH pad, find the used layers (track ends within the pad radius, plus SMD pads hit).
2. Map each to its reference set. If the set is unchanged, the via is fine (Ott case 2).
3. Same net: report the nearest via spanning both planes. Extra loop ≈ d × separation; limit ≤200 mil (preferably 1–2 mm), rate-scaled.
4. Different nets: find the best-loop capacitor, warn 5–10 nH, and recommend re-layering.

**D. Loop area**
- A = Σ length·h + detour area (shoelace) + Σ d_via·Δz.
- Screen with Ott's differential-mode E at harmonics up to the knee (I = V/Z0).
- Use it for **ranking only**; the cable common mode dominates.

**E. Crosstalk**
1. Hash segments spatially.
2. Pair those within ≤5° of parallel; D = s + (w1 + w2)/2; include broadside pairs.
3. Compute K × min(1, 2T/t_r), plus microstrip FEXT ∝ L/t_r.
4. Sum per victim (two nearest plus the next two).
- Use stricter budgets for I/O and analog victims.
- EMI Guardian's (h/s)² is a cruder proxy.

**F. Connectors**
1. Reference point = centroid of the ground/shield pins.
2. Edge-band or corner cluster score (maximum pairwise distance, angular spread).
3. For each fast net, classify which side each connector is on, then compute MREMC L_ret → V_cm → E_max.
4. Flag within 6 dB of the limit, or V_cm >1 mV (100 µV for strict limits).
- Use it as both a placement cost and a post-route check.

**G. Stitching**
1. Clip the GND vias spanning a plane pair to the overlap of both fills.
2. Find the **largest empty circle** (Voronoi) and its diameter d_max.
3. Require c/(2√εr·d_max) > f_knee. For apertures and fences, d_max ≤ λ/20.
4. Prefer distributed vias.
- For GUARD fences, check the maximum gap along the offset polyline. The master generator can build fences.

**H. Via stubs**
1. Take z-depths from the stackup.
2. Use the drilled span minus backdrill, and the used span from attached tracks.
3. Stub = barrel beyond the used span + pad rings + unremoved NFPs.
4. f_res = c/(4·stub·√εr). Flag if > min(15 mil, 0.3/Gbps), or if f_res < 3× Nyquist.
- Shares its stackup model with the KiCad 10 via delay.

**I. Other checks**
- I/O corridor.
- TVS/filter/CMC nearer the connector than the IC, with a short GND via.
- Floating copper and islands.
- Clock edge/period <10%.
- Series R near the driver.
- Running skew.

**[IF] geometric functions**
- Path order with zero vias.
- Offset-polygon GND coverage.
- No T-junctions or test points.
- Distance windows and annuli.
- Plane-edge offset (or a shrunken keep-in area).
- Loop polygon → L → overshoot L·dI/dt (warn at >0.2·Vds_max).
- Trace capacitance (crystal, I2C C_b).
- AC cap near either endpoint.
- Edge-finger keep-outs.

**Simulation (S)**
- Loss budgets.
- DDR IBIS PVT.
- Termination current.
- 3-D guard analysis.
- MREMC pre-screen.
- Field-solved width and gap.

### Encodability matrix

| Rule family | KiCad 9/10 | KiCad master | External |
|---|---|---|---|
| Width/gap per layer for Z0 | native `(layer …)` | same | S: field solve |
| Pair/bus skew, DDR segments | native (ps, `fromTo`) | same | — |
| Length/delay across series parts | partial | `net_chain_length` | — |
| Uncoupled length, vias, edge, angles | native | native | — |
| Return path on one layer | — | `return_path` | G: auto layer, buffers, detours |
| Reference change → via/cap | — | — | G (C) |
| Loop area | — | — | G (D) |
| Trace stubs | — | `stub_length` | G for plain nets |
| Via stubs | backdrill model only | — | G (H) |
| Crosstalk coupled length | clearance only | — | G (E) |
| Connector clustering/between | — | — | G (F) |
| Stitching/fence pitch | — | generator | G (G) |
| Protection topology; plane-edge offsets | rule areas, partly | — | G (I) |

### Open-source checkers (licence gates reuse)

| Project | Licence | Content |
|---|---|---|
| [jasonarnoldarnie/kicad-tools `return_path`](https://github.com/jasonarnoldarnie/kicad-tools) | **None → reference only** | KiCad 10 SWIG + numpy. Reference = nearest filled layer by dielectric. Samples every 0.1 mm on a 0.05 mm raster. Flags: VOID (A* detour, fail >1.0 mm), ISLAND, SPLIT, TERMINAL, VIA (via fail >2 mm; cap fail >5 mm), EDGE (w/2 + 3h). Loop-area model; HTML glow 1/(1+(x/h)²) to ±3h; `return_path_classes.json` overrides; plane copper only |
| [aklofas/kicad-happy](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md) | MIT | Claude Code/Codex skill; 44 rules in 18 categories: voids, GND-via-less transitions, edge < h, stitching √(area/count) vs λ/20 at 3× crystal frequency, 3H crosstalk (≥5 mm), skew→CM, ESD, connector filtering and ground-pin ratio, cavity, harmonics, PDN. Risk score 0–100 (≤3 per rule); band and interface ranking; near-field probe points |
| [hap231/kicad-emi-guardian](https://github.com/hap231/kicad-emi-guardian) | MIT | KiCad ≥10.0.5 IPC: gaps/detours; return vias 2 mm; coupling (≤5°, ≥5 mm, ≤0.5 mm, grid hash); edge 1 mm; skew 1 mm; acute <75°; stubs ≥0.8 mm; long nets (1/6); GND-pour appendage antennas ≤1500 MHz; stitching planner; dry-run, no markers |
| [tombueng/emcvisual](https://github.com/tombueng/emcvisual) | 0BSD-style | Browser TS; reads KiCad 6–10, IPC-2581, ODB++, Eagle. Biot–Savart with images. ~30 rules, each with threshold, origin and test board (return-gap, ref-change, no-stitching 3 mm, edge, cable-cm, io-coupling, long-line with no ≥10 Ω within 15 mm, filters, ESD, crystal, hot loop). Ranks by far-field share; full-wave comparison unreviewed |
| [RolandWa/KiCAD_Custom_DRC](https://github.com/RolandWa/KiCAD_Custom_DRC) | **Non-commercial proprietary → reference only** | TOML: GND via ≤2 mm; decap ≤3 mm; plane sampled every 0.5 mm in a 1 mm band; edges; 3W; connector filters; IEC 60664-1 creepage |
| [easyw/RF-tools-KiCAD](https://github.com/easyw/RF-tools-KiCAD) | GPL-3.0 | Via fence (pyclipper), stitching, teardrops |
| rjwalters/kicad-tools | unchecked | Protocol-aware native pair rules [S] |

KiCad itself is GPL-3.0+; kipy is MIT.

**Commercial checkers:**
- **HyperLynx DRC** (parameterised): edge rate, edge shield, exposed length, filter placement, ICs over a split, I/O coupling, metal island, gap crossing, plane edge, reference change, via stub.
- **Others:** NEC EMISTREAM; IBM EMSAT (Archambeault; "hundreds of man-years" [S]); Zuken CR-8000 EMC Adviser.
- **Net info sources:** manual entry, name substrings, component database, or IBIS. Names alone are insufficient ([LearnEMC](https://learnemc.com/commercial-emc-rule-checkers)).
- **Clemson:** source/path/antenna combinations are computer-identifiable from the layout plus component data [S].

### Implications for our system
- **Checker priority:**
  1. B (return path)
  2. C (reference change)
  3. H (via stubs)
  4. F (connector between-ness)
  5. E (crosstalk incl. I/O)
  6. G (stitching)
  7. I (protection/islands/edge rate)
  8. D (loop ranking)
- Reimplement from these specs; copy code only from MIT, 0BSD or GPL-compatible projects.
- Emit native constraints first: KiCad 10 ps/`fromTo`; master `return_path`/`stub_length`.

---

## 9. Rule-pack format and knowledge-base schema

**Five parts per rule** ([IF] §11):
1. Match pattern to schematic objects.
2. Typed parameters (mm/mil/ps/Ω/nF/pF/dB/%/UI/W/H or formula).
3. Provenance and precedence: datasheet > vendor family > interface default > generic. **Record conflicts; never resolve them silently.**
4. Backend: `kicad_dru`, `geometric`, `simulation` or `bom`.
5. Placement intent, separate from routing: anchor, adjacent, order_along_path, distance_window, same_side, keepout_ring, orientation, max_loop_area or priority_order.

**YAML v0** (precedence: fab 10 < interface 20 < vendor family 30 < datasheet 40):
- `pack{id, version, precedence, vendor_profile}`
- `applies_when{parts[{role, match{lib_regex, pin_functions, value_regex, class, nets}, optional}], nets[{role, match{pin}}]}`
- `parameters{name: {value|formula, unit, tol_pct, tag P|S|D, source, rev, by_vendor{}}}`
- `conflicts[{parameter, values[{value, source}], resolution: stricter|vendor_profile|window|ask}]`
- `placement`, `routing{netclasses, diff_pairs}`, `checks[{id, backend, severity, emit}]`, `overrides`

**Resolution:**
1. Highest precedence wins.
2. Then `by_vendor[profile]`.
3. Then the declared resolution. The default is "stricter", with an `info` finding citing both sources.
4. **[S] never overrides [P]** at equal precedence.
5. [D] values default to warning until calibrated.

**Worked examples ([IF]):**
- **usb2_hs:**
  - Roles: conn, phy, esd, cmc.
  - Parameters: zdiff 90 ±15% (`by_vendor`); skew 1.27 mm (Qualcomm 2.0, TI controllers 3.81); length warn 150 / max 250 mm (TI 304.8); ≤4 vias; gaps 0.762/1.27 mm; GND overhang 5× gap; esd_conn_max 5 mm [D].
  - Conflict: shield → ask.
  - Placement: anchor the connector to the edge; order conn→esd→cmc→phy.
  - Checks:
    - DRU: `skew … within_diff_pairs`, `via_count`, `length` + `fromTo`, clearance.
    - Geometric: no T-junctions or TPs; GND coverage; ESD path order + GND via ≤1 mm.
    - BOM: no series caps.
- **buck_sync:**
  - Parameters: Cin ≤2 mm; bulk ≤20 mm; loop 2/10/20 mm²; 5 A/ns; L1–L2 ≤0.127 mm; 1 via/A; 1 mm/A; SW ≤2.54 mm; FB ≤3 mm [D].
  - Placement: same side; inductor keep-out ring.
  - Override: datasheet reference layout at precedence 40, with the loop target measured from the evaluation board.
- **xtal_pierce:**
  - Placement: annulus from the vendor minimum to 12 mm; caps adjacent, CL1 first; series R by the MCU.
  - Parameters: parasitic limits; hs_keepout 3 mm [D]; metal-can vendor switch.
  - Routing: GND ring tied once; XIN/XOUT ≥3W [D]; no TPs.
  - DRU: disallow foreign tracks and vias in `XTAL_KEEPOUT`.
- **Caveat:** the `within_diff_pairs`, `insideArea` and `track_angle` forms must be tested on the installed KiCad.

**Knowledge-base record** ([HS] §12 + [VR]):
- `rule_id, family, statement`
- `numeric{value, unit, basis: mm|ps|W|h|λ|fraction_of_tr}`
- `physics_why`
- `applies_if{interface, t_r<, data_rate>, layer_type, enclosure, emission_class}`
- `severity, check_type{K, K11, G, S}, kicad_dru_template, checker_fn`
- `source_url, source_author, source_type{physics, rule-of-thumb, vendor-req, spec-req, measured, satirical-inverse}, provenance{P, P-code, S}, confidence`
- `conflicts_with[]`, plus `source_scope`, `statement_strength`, `contested_by`
- Negative (myth) rules are included.

**Net classification:**
1. Regex seeds: USB/PCIe/HDMI/MIPI/DDR/QSPI/clock/MDI, `_P/_N`, `+/-`, `_t/_c`.
2. LLM confirms from pin function and datasheet.
3. User overrides (`return_path_classes.json`-style).
4. Assign a t_r; treat every pin of a fast IC as noisy.

### Implications for our system
- One interface/net-class table drives both the native KiCad constraints and the Python checker suite. Every emitted rule carries `rule_id`, `source_url` and `provenance`.
- Packs are data, so they can be calibrated later against vendor evaluation-board layouts.

---

## 10. Idea inventory

Tags: [HS] rules_highspeed_emi.md; [IF] interface_rule_packs.md; [VR] verification_rules.md.

**Physics and modelling**
1. Encode physics, not slogans; myths become negative rules [HS].
2. Return flows directly under the trace → continuous-reference rule [HS].
3. ±1h/±3h/±10h spread justifies edge and void offsets (1.5W ≈ 3h) [HS].
4. A via through the same plane is not a discontinuity [HS].
5. Merge antipads into voids; measure slot length perpendicular to the trace [HS].
6. Ott's 4-level layer-change order as router policy [HS].
7. Return vias ≤200 mil, rate-scaled ~5/2.5/1.3 mm [HS][IF].
8. Stitching caps (≤1 µF) only at split crossings; 1–10 nF/50 mil is not primary [VR].
9. Avoid power-plane references; never overlap non-referencing planes [HS].
10. No ground traces or fill on plane boards; direct ground vias [HS].
11. 10:1 signal:ground vias (3-D scaling) [HS].
12. Pairs return per leg; apply return rules to each [HS].
13. Skew→CM formula (20% → 10%) [HS].
14. Critical length: t_r/6 flag, t_r/2 terminate (contested) [HS][VR].
15. Slow edges first; default series R; t_r ≈ 20% of UI [HS].
16. Termination chosen for minimum harmonic current [HS].
17. Stub limit min(15 mil, 0.3/Gbps), pad rings included [HS][VR].
18. Stub strategy decided before stackup [HS].
19. Non-stub pad entry; TH receptacles entered from the bottom [HS][VR].
20. Johnson K with saturation and aggressor sum [HS].
21. Spacing from K budget: D ≥ H√(1/K−1) [HS].
22. Cut crosstalk via h first [HS].
23. Guards only in stripline, end-shorted and length-matched [VR].
24. Stricter crosstalk budgets for I/O and analog victims [HS].
25. Orthogonal adjacent signal layers [VR].
26. Antenna model; 1 mV/100 µV between antenna parts [HS].
27. MREMC as computable CM-EMI estimator [HS].
28. Ott DM/CM formulas; 5/15 µA cable limits [HS].
29. FCC 15.109 as the E_max target [HS].
30. 1 mV / 3.6 µA / Class B consistency checks [HS].
31. Cavity-resonance formula for stitching [HS].
32. No spread-spectrum reference for transceivers, PLLs or RF [HS].
33. All pins of fast ICs are HF sources [HS].

**Stackup**
34. Ott's four factors and five objectives; 8-layer minimum [HS].
35. 4/6/8/10-layer candidate library [HS].
36. 8-step stackup selection and scoring [HS].
37. Ott-vs-Hartley 6-layer as a warning with rationale [HS].
38. Penalise forced P↔G changes [HS].
39. Plane pair <0.25 mm when ≥3 power pins share a rail [HS].
40. Power planes on one layer; gap ≥ plane-to-ground spacing (≥3 mm "maybe") [HS][VR].
41. Stackup before placement [HS].
42. Microstrip vs stripline is a context switch [VR].
43. Fibre weave: 10–35° rotation or zig-zag [VR].
44. Ott impedance/delay rules of thumb as fallback [HS].
45. Fab stack and material data as inputs [IF][VR].

**Differential pairs**
46. skew_max = min(spec, 0.1·t_r) via per-layer delay [HS].
47. Running-skew compensation near the mismatch [HS].
48. Pair exit and entry in the same direction [HS].
49. Switchbacks ≪⅓ t_r or uncoupled; jogs ≥3W; spread <2S [HS][VR].
50. Coupling tighter than 0.5 mm gives no extra EMI benefit [HS].
51. GND vias pinning planes at differential vias (XFP) [HS].
52. 30 mil (signals) / 50 mil (clocks) absolute keep-outs [VR].
53. Uncoupled ≤45 mil; breakout ≤0.25 in [VR].
54. Equal via counts; family-scoped via limits [VR].
55. 30 mil antipads; no NFPs [VR].
56. Symmetric 0402 in-line parts; 100%, 2-layer pad voids [VR][IF].
57. Bends >135°, balanced [VR][IF].
58. KiCad pair-to-pair clearance condition [HS].

**Interface packs**
59. Mandatory vendor profiles; tightest [P] + info when unknown [IF].
60. Chain order connector→ESD→CMC→AC cap→PHY [IF].
61. Qualcomm 5 ps as relaxed USB3 option [IF].
62. ~25–50 mm per-via SerDes length penalty [IF].
63. ESD+CMC ≈1 in length cost [IF].
64. USB shield conflict → ask user [IF].
65. Type-C CC width, capacitance window, no passives [IF].
66. PCIe L_max from budgets and material tables [IF].
67. AC cap at either endpoint, never mid-line [IF].
68. 176–220 nF universal Gen3+ window [IF].
69. Edge-finger inner keep-outs [IF].
70. Lane matching only on device demand [IF].
71. DDR: one `fromTo` rule per SDRAM per group [IF].
72. Never emit cross-byte DDR skew [IF].
73. 20% derating as opt; limit as max; IBIS check [IF].
74. Micron 1%-of-period default [IF].
75. Stackup delay model, not a fixed ps/mm [IF].
76. Ethernet PHY↔magnetics soft window (~25 mm; >76 error) [IF].
77. Ethernet ESD location as a pack parameter [IF].
78. Chassis island / Bob Smith as clearances [IF].
79. UI-based skew formulas [IF].
80. D-PHY length table + `cable_il_db` [IF].
81. SATA polarity is controller-dependent [IF].
82. CAN/RS-485 end-node termination; in-path protection [IF].
83. I2C pull-up window from stackup C [IF].
84. SD CLK↔data matching; source series R [IF].
85. Slow-clock star and daisy limits [IF].
86. Crystal annulus placement [IF].
87. Crystal parasitic score from trace C [IF].
88. Crystal can/under-copper conflicts as vendor switches [IF].
89. C-shaped GND ring at clock/RF vias [IF].
90. Buck: Cin <2 mm, loop tiers, L→overshoot [IF].
91. Inductance anchors make loop size scoreable [IF].
92. Datasheet layout override at precedence 40 [IF].
93. Fab packs min-only; never relaxed [IF].
94. Derived mounting-hole keep-out (RP2040 6 mm) [IF].

**EMC placement**
95. Cabled connectors on one edge or corner [HS].
96. No HS between connectors (MREMC-scored) [HS].
97. 2 cm I/O-zone defaults [HS][VR].
98. Clear I/O corridor; no HF under I/O parts [HS].
99. I/O nets end in a series or filter part [HS].
100. TVS topology as comparative constraints [VR].
101. TVS GND via adjacent; ESD corners ≤45° (2.6 mm) [VR].
102. Via only after the TVS (Case 1) [VR].
103. CMC ≲5 mm as soft target [VR].
104. Edges: 90 mil to plane edge; 2X to board edge; 3W [VR].
105. Plane-edge offset as a zone-boundary check [VR][IF].
106. Largest-unstitched-region metric reconciles stitching debate [HS].
107. Split-boundary stitching 10–15 mm (soft) [VR].
108. Chassis bond: overlap layer + SMT caps + one LF tie [HS].
109. One partitioned ground; ≥14-bit isolated regions joined under the ADC [HS].
110. 300 mV check only for deliberate splits [VR].
111. Optional filter/TVS/shield footprints [HS].
112. Two EMC reviews: pre-layout and first draft [HS].
113. Visualise each compliance test's current path [HS].
114. Clamp-measure every cable [HS].
115. Ott red flags as lint; invert the maximize-emission list [HS].
116. emcvisual placement thresholds [HS].
117. 7-step placement order (1–3 hard) [HS].
118. Placer costs: V_cm, I/O intrusion, length, crossings, alignment [HS].

**Classification and verification**
119. Hard / soft-strong / soft-weak / context-switch tiers [VR].
120. Blog mm values become rank objectives [VR].
121. `source_scope` / `statement_strength` / `contested_by` fields [VR].
122. LLM turns relative wording into comparative constraints [VR].
123. Severity recalibrations (TL-5, EMI-7, EMI-6, RF-05) [VR].
124. Corner rule scoped to ESD/RF classes [VR].
125. Contested rules never default [VR].
126. Montrose conditions as the 20-H selector [VR].
127. Part-specific numbers stored per part [VR].

**Encoding and checkers**
128. KiCad 10 ps + `fromTo` constraints [HS][IF].
129. Emit master `return_path`/`stub_length` when available [HS].
130. Checker A: reference map [HS].
131. Checker B: return continuity, A* detour [HS].
132. Checker C: reference-change via/cap [HS].
133. Checker D: loop ranking [HS].
134. Checker E: crosstalk via spatial hash [HS].
135. Checker F: connector clustering and between-ness [HS].
136. Checker G: largest empty circle vs cavity and λ/20 [HS].
137. Checker H: via stubs and f_res [HS].
138. Checker I: protection, islands, edge rate, corridor [HS].
139. [IF] geometric functions (order, coverage, windows, loop L, trace C) [IF].
140. HTML/JSON overlay (no IPC DRC markers) [HS].
141. Stackup from `.kicad_pcb` or IPC `get_stackup` [HS].
142. Master GUARD generator for via fences [HS].
143. Licence gating for code reuse [HS].
144. Rank findings by consequence [HS].
145. Expert-system framing over full simulation [HS].

**Format and knowledge base**
146. Five-part rule definition [IF].
147. YAML packs with `by_vendor`/`conflicts`/`resolution` [IF].
148. [S] never overrides [P]; [D] defaults to warning [IF].
149. Knowledge-base schema with `basis` (h, λ, fraction of t_r) [HS].
150. Net classification: regex → LLM → user [HS].
151. Per-net t_r, flagged when estimated [HS].
152. Calibrate [D] values on vendor evaluation boards [IF].
153. Test emitted DRU syntax on installed KiCad [IF].
154. Closing the constraints→route→check loop is unoccupied [HS].
