# Digest: High-Speed/SI, Differential Pairs, EMI/EMC, Stackup and Interface Rule Packs

**Inputs:**
- `rules_highspeed_emi.md` **[HS]**, read in full.
- `interface_rule_packs.md` **[IF]**, read in full.
- `verification_rules.md` **[VR]**: §1A, the §1B crystal and edge rows, the §2 HS/EMC/RF/DFM additions, and the §3 classification.

**Where VR conflicts with HS or IF, the VR value is used here and marked.**

**Tags:**
- **[P]**: primary source, read in full.
- **[P-code]**: read from source code.
- **[S]**: search snippet only.
- **[D]**: derived by the note author.
- **VR statuses:** VERIFIED; +CTX (correct, but a condition was dropped); CORRECTED; CONTESTED; NOT FOUND; NOT RETR. (could not be retrieved).

**Units:** 1 mil = 0.0254 mm. W = trace width. h or H = height to the reference plane. t_r = rise time. UI = unit interval.

---

## 0. Bottom line

1. **One physical model is shared by all the primary authors.** Ott, Hubing/LearnEMC, Bogatin, Johnson, Hartley and Archambeault agree on three points:
   - Energy lives in the dielectric fields.
   - High-frequency return current flows in the adjacent plane, directly under the trace.
   - Radiated EMI comes from common-mode voltage between two "antenna parts" (cables, chassis), and from imbalance or skew.
   
   So we should encode the physics, not the slogans. Hubing: "a board that complies with 90% of the guidelines may be much worse than a board that complies with only one or two" ([LearnEMC](https://learnemc.com/why-you-should-be-cautious-about-using-emc-design-guidelines) [P]).
2. **Vendor values for the same interface differ by 5–25×.** Examples:
   - USB3 intra-pair skew: 2 mil vs 0.7 mm.
   - DDR4 DQ↔DQS: 2 ps vs 25 ps.
   - Ethernet PHY↔magnetics: ≥25 mm vs <25 mm.
   
   Vendor profiles are therefore mandatory. When the vendor is unknown, use the tightest primary value and raise an `info` finding.
3. **VR found that numbers from named vendor app notes mostly hold.** The usual defect is a dropped applicability condition: device family, data rate, enclosure vs PCB, or a single measured part. Rule records therefore need `applies_if`, `source_scope`, `statement_strength` and `contested_by` fields.
4. **Blog-only millimetre thresholds were never confirmed by a primary source.** These include TVS ≤5–10 mm, crystal ≤5 mm, CIN ≤0.5–1 mm, RF↔SMPS 20 mm, and stitching 3–5 mm. Treat them as ranked or comparative objectives, never as DRC errors.
5. **KiCad covers part of the problem natively:**
   - **KiCad 10** natively checks most skew, length and delay rules: ps units, `fromTo()`, per-layer and via delay, and backdrill.
   - **KiCad master** (unreleased) adds `return_path`, `stub_length`, net chains and a via-stitch generator.
   - **Everything else** needs custom geometric checkers (algorithms A–I, §8) or simulation budgets.
6. **Nothing closes the loop today.** No public system generates constraints, routes, and then physics-checks inside KiCad. Every tool reviewed is a post-layout checker or a generator ([HS] §12).

---

## 1. Physics fundamentals: return paths, loop area, rise time, crosstalk, radiation

### 1.1 Where return current flows

- **Bogatin.** Above the frequency where ωL dominates, the return flows "directly underneath the signal currents", because that path has the lowest loop inductance ([LeCroy](https://www.teledynelecroy.com/oscilloscope/blog/signal-return-paths-signal-and-power-integrity-tutorial/) [P]). His Rule #7: "always use a continuous return path adjacent to every signal path" ([SIJ](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers) [P; VERIFIED]).
- **Ott.**
  - The return flows in the plane directly underneath, whether that plane is power or ground.
  - Above 30 MHz (1 oz copper) these are surface currents, so a plane acts as two conductors ([Ott P6](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html) [P]).
- **Hartley.**
  - A signal on L1 returns 100% in an adjacent L2 ground, even if the board has 20 planes.
  - Two or three signal layers sharing one plane leave "all fields intermingling … one of the places where EMI comes from" ([Altium](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley) [P; VERIFIED as a paraphrase]).
- **Spread (Adamczyk).**
  - Microstrip: 50% of the return lies within ±1h, 80% within ±3h, 97% within ±10h.
  - Symmetric stripline: 99% within ±3h, with about 75% on the nearer plane ([In Compliance](https://incompliancemag.com/pcb-return-current-distribution-in-a-microstrip-line/) [P]).
  - Because w ≈ 2h at 50 Ω, TI's "1.5 W from voids" is about 3h, so it is the same physics.
- **Johnson.**
  - "Signals closest to a good return suffer the least ground bounce", so spread return pins among signal pins ([P](https://www.sigcon.com/Pubs/edn/SpreadYourReturns.htm)).
  - **3-D scaling:** a 0.063" via at 500 ps behaves like a Euro-connector at 5 ns, so it needs a 10:1 signal-to-ground ratio. Hence a "carpet of vias" ([P](https://www.sigcon.com/Pubs/edn/ConnectLayers.htm)).
- **Differential pairs are not self-returning.** Each leg returns under itself.
  - Johnson's 2.5 Gb/s XAUI case: a pair referenced to a power plane, with SMA grounds on ground, gave a "horrible" eye.
  - The fix was a ground island under the connectors, with a 6 mil gap and the pair about 12 mil apart at the crossing ([P](https://www.sigcon.com/Pubs/edn/ReturnCurrentMatters.htm)).
- **Archambeault.** A via that changes reference "greatly magnif[ies]" the common-mode current ([P](https://www.sigcon.com/Pubs/edn/ReducingEmissions.htm)).
- **LearnEMC.**
  - The return follows least inductance at MHz and least resistance at kHz.
  - "Radiation is NOT proportional to loop area": properly designed long lines need not radiate ([P](https://learnemc.com/the-most-important-emc-design-guidelines)).

### 1.2 Discontinuities: splits, slots, voids, reference changes

- **Bogatin's trifecta for a split:** a reflection, ground bounce plus shared-path crosstalk, and EMI from the voltage across the plane. The only benefit of a split is low-frequency resistive isolation, and only with the gap parallel to the signals and never crossed [P].
- **Ott's slot measurements** ([Slots](https://hott.shielddigitaldesign.com/techtips/tips-slots.html) [P]): plane voltage across 1" under a 10 MHz trace with 3 ns edges.

  | Slot under the trace | Plane voltage |
  |---|---|
  | none | 15 mV |
  | ¼" | 20 mV |
  | ½" | 26 mV |
  | 1" | 49 mV |
  | 1.5" | 75 mV |
  | Row of 15 holes of 0.052" over 1" | 15 mV |

  - So merged antipads act like a slot, while isolated holes do not.
  - Ott also suggests etching one board set without laminating it, to inspect the buried planes.
- **Ott's layer-change order**, best to worst ([P](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html)):
  1. Stay on one layer.
  2. Change between two layers adjacent to the same plane. A via through that plane is *no* discontinuity, because the antipad wall joins the plane's two surfaces.
  3. Change between same-net planes, with a ground via "immediately adjacent".
  4. Change between different-net planes. The return then goes through the nearest decap, which adds 5–10 nH. Interplane capacitance only helps "considerably above 500 MHz".
- **Return vias.**
  - TI: "symmetrically within 200 mils (center-to-center, closer is better)" whenever the same GND reference cannot be kept ([SPRAAR7J p.8](https://www.ti.com/lit/pdf/spraar7) [P; VERIFIED]). The 40 mil and 1 mm figures are [S].
  - TI Gen5: within 50 mil, "as many as possible" ([SNLA426](https://www.ti.com/lit/pdf/snla426)).
  - EMA: at least 2 vias within 100–200 mil, on both sides of a pair ([EMA](https://www.ema-eda.com/wp-content/uploads/2025/10/PCIe-Design-Guide-Part-1.pdf)).
  - Renesas: adjacent, but not close enough to disturb the impedance ([R31AN0080](https://www.renesas.com/en/document/apn/pcie-buffer-mux-layout-recommendations?r=1565126)).
  - Qualcomm: a C-shaped GND via ring at every clock and RF transition ([CXO](https://docs.qualcomm.com/doc/80-PV086-5P/topic/CXO-and-SLEEP_CLK-routing.html)).
  - Scale by data rate [IF, D]: about 5 mm up to 5 Gb/s, about 2.5 mm at Gen3/4, about 1.3 mm at Gen5.
- **Stitching capacitors.**
  - **VR CORRECTED:** the catalog's "1–10 nF within 50 mil at GND↔PWR changes" is secondary only ([AtlasPCB](https://www.atlaspcb.com/blog/pcb-via-transition-return-current-path-signal-integrity/) [S]).
  - The primary TI value is for *split crossings*: "1 µF or lower … as close as possible" ([SPRAAR7J p.7](https://www.ti.com/lit/pdf/spraar7)).
  - Ott, for slot crossings: 0.001–0.01 µF within 0.1" on each side. If both power and ground are split, allow no crossings at all [P].
  - u-blox gives no value: "some capacitors … and an adequate number of GND vias" ([NORA-B2](https://content.u-blox.com/sites/default/files/documents/NORA-B2-u-connectXpress_SIM_UBXDOC-465451970-3906.pdf)).
  - TI SLLU149E: place bypass caps next to the vias when the reference changes.
- **TI SPRAAR7J rules:**
  - Keep ≥1.5 W from voids [VERIFIED+CTX: this applies to HS differential pairs and is waived at intentionally voided SMD pads].
  - "TI does not recommend high-speed signal references to power planes" [VERIFIED].
  - Never overlap planes that do not reference each other.
- **Splits.** If a split is unavoidable, use one bridge and route every crossing over it ([Ott](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html); [TI SLYT512](https://www.ti.com/lit/an/slyt512/slyt512.pdf) [VERIFIED]).
- **HyperLynx DRC "interrupted return path"** covers three cases: a gap crossing; running near a plane edge (the board edge or a large void); and a reference change. A P↔G change needs a capacitor; a G↔G change needs a via ([whitepaper](https://schematicsforfree.com/files/Manufacturing%20and%20Design/PC%20Board%20Design%20and%20Fabrication/PCB%20Design,%20Layout%20&%20Routing/USING%20HYPERLYNX%20DRC%20TO%20FIND%20EMI%20ISSUES.pdf) [P]).
- **LearnEMC** ([PCB Layout](https://learnemc.com/pcb-layout) [P]):
  - A gap crossing is a *conducted* common-mode source that drives the cables on either side.
  - With solid planes, use no ground traces or fill on other layers; connect ground with a via directly to the plane.
  - Never filter by routing over a gap or by putting a ferrite on ground.
  - Clemson EMCS97-159: longer gaps raise common-mode current [S; NOT RETR.].

### 1.3 Radiation mechanisms and thresholds

- **Antennas (LearnEMC).** An unintentional antenna needs two parts that are not electrically small, with a voltage between them.
  - Below about 100 MHz, only cables and chassis qualify.
  - Above 100 MHz, tall parts, heatsinks, seams and sparse planes also qualify. ICs, traces and dense planes are poor antennas.
  - **About 1 mV between antenna parts can fail Class B; requirements stricter than CISPR 32 B may need 100 µV** ([P](https://learnemc.com/pcb-layout); VERIFIED).
- **Magnetic coupling between connectors.** A trace's return flux wraps the plane.
  - "Tens of milliamps at tens of megahertz" induces millivolts across the plane, rising with trace width and height. Stripline induces none.
  - Fixes: put all connectors on one edge, or bond a chassis at both connectors.
- **MREMC common-mode algorithm** (Hubing/Su/Zhu calculator, [CMode_algr.js](https://learnemc.com/ext/calculators/mremc/calculator/CMode_algr.js) [P-code]):
  - Return inductance: L_ret = (µ0/π)·t·l_t/w_e/√(1 − 4(1 − 2t/w_e)·offset²/w_e²), with w_e = d1 + d2 (distances to the two board edges) and offset = |d1 − d2|/2.
  - Trace inductance and imbalance: L_trace = √(µ0ε0)·l_t·Z0, and h = L_ret/(L_ret + L_trace).
  - Common-mode voltage: V_cm = h·V_dm (voltage-driven), or 2πf·L_ret·I_dm (current-driven, with I_dm = V/R_L or V·2πf·C_L).
  - Field: E_max = F_max·0.55·V_cm·boardfactor·cablefactor.
    - boardfactor = sin(2πL_eff/λ) if λ ≥ 4L_eff, else 1.
    - cablefactor = sin(2π·1 m/λ) if λ ≥ 4 m, else 1.
    - F_max = 2/sin(√(c/(f·L_cable))) above the cable's half-wave resonance.
  - Assumptions: unshielded, cable ≫ board, about 1 m above ground.
- **emcvisual's simpler variants** ([RULES.md](https://github.com/tombueng/emcvisual/blob/main/docs/RULES.md) [P-code]):
  - Cable common mode: L_p = (4/π²)µ0·l·h/(d1 + d2), V = ωL_p·I, E = 0.365·V (Hockanson/Hubing 1996).
  - I/O coupling: M = µ0/(4π)·ln(1 + 4h²/s²), E = 40·V/Z_ant, with Z_ant = 80(N+1) Ω.
- **Ott's formulas**, via kicad-happy ([MIT](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md) [P-code]):
  - Differential-mode loop: E = 2.632×10⁻¹⁴·f²·A·I/r.
  - Common-mode cable: E = 1.257×10⁻⁶·f·L·I_CM/r.
  - Doubling loop area adds 6 dB; doubling frequency adds 12 dB.
- **Cable common-mode current limits.**
  - Ott: <5 µA for Class B and <15 µA for Class A, for cables ≥1 m (a 0.5 m cable allows 10 µA). Measure with a clamp (F-33-1, 2–250 MHz) and iterate over every cable ([Ott](https://hott.shielddigitaldesign.com/techtips/tips-cm.html) [P]).
  - Hartley: 8–10 µA fails Class B.
- **FCC §15.109 limits** ([CFR](https://www.law.cornell.edu/cfr/text/47/15.109) [P]):
  - Class B at 3 m: 100 / 150 / 200 / 500 µV/m for 30–88 / 88–216 / 216–960 / >960 MHz.
  - Class A at 10 m: 90 / 150 / 210 / 300 µV/m.
- **Consistency checks [HS, D].**
  - Ott's common-mode formula at 100 MHz (1 m cable, 3 m distance) against 150 µV/m gives about 3.6 µA, consistent with the 5 µA rule.
  - MREMC with V_cm = 1 mV gives about 61 dBµV/m, roughly 20 dB over Class B. So 1 mV is a hard line.
- **Cavity resonance.** f_mn = (c/2√εr)·√((m/L)² + (n/W)²), independent of plane spacing ([calc](https://learnemc.com/ext/calculators/cavity_resonance/pcb-res.html) [P]).
- **Spread-spectrum clocks (Johnson).** They lower peak readings when the spectral lines end up more than 100 kHz apart. Never use one as the reference for transceivers, PLL CPUs or RF ([P](https://www.sigcon.com/Pubs/edn/clockmod.htm)).

### 1.4 Rise time, critical length, termination, stubs

- **Critical length [CONTESTED per VR].**
  - Johnson: termination is commonly needed somewhere between 1/10 and 1/3 of t_r. At ½ t_r, "severe overshoot and ringing" occurs. He simulates anything over 1/6 ([P](https://www.sigcon.com/Pubs/news/3_14.htm)).
  - LearnEMC and ADI MT-097: terminate at ≥t_r/2. MT-097's conservative rule is 2 in per ns; 2" of microstrip at Er = 4 is about 270 ps ([MT-097](https://www.analog.com/media/en/training-seminars/tutorials/MT-097.pdf)).
  - **Resolution: at t_r/6, flag the net for SI review; at t_r/2, it must be terminated.**
- **Slow the edge first (LearnEMC)** ([P](https://learnemc.com/not-so-good-emc-design-guidelines)):
  - Use matched termination only as a last resort.
  - Default to a series R on capacitively loaded digital nets, and remove it where it is clearly not needed. Use resistors, not ferrites.
  - Aim for a transition time of about 20% of the UI. "100 MHz … should never fail at 2 GHz."
  - Reject these as decision criteria: "terminate beyond λ/4", "series R above 1 V/ns", "Z ≥ Z0/4".
- **Archambeault.** On a 12" trace at 133 MHz, moving the source termination from 10 Ω toward 39 Ω cut harmonic current by 10–20 dB. Choose the termination for **minimum current**, not just an acceptable voltage waveform.
- **Stub limits.**
  - Ott: L[in] ≤ t_r[ns].
  - Bogatin, via Telian: the ¼-wave stub length is 3/Gbps inches, so play it 10× safe with **<0.3/Gbps** ([SIJ](https://www.signalintegrityjournal.com/articles/2962-fixing-the-problem-of-stubs) [P; VERIFIED]).
  - Telian's demo: 12" at 12 Gb/s with a 0.250" stub passes <2% at 6 GHz; a 0.025" stub has no visible effect.
  - At 30 Gb/s the limit is about 10 mil. A non-backdrilled via stub is 11 mil (4 + 3 + 4). Count the middle pad ring even on backdrilled vias. "50 mils is too long for even an 8 Gbps stub."
- **Other stub numbers.**
  - f ≈ 1.5/L[in] GHz [S; EDN NOT RETR., but arithmetically consistent].
  - TI: <15 mil, otherwise backdrill [VERIFIED].
  - TI Gen5 hard maximum: about 54 mil (Megtron 6) or 51 mil (FR4).
  - EMA: a 20 mil stub resonates at 8–16 GHz.
  - LPDDR4 via stubs: ≤20 mil (CA) and ≤40 mil (data).
- **Alternatives to backdrilling:** route on near-outer layers (L1 to L15 of 16), use sequential lamination, or use blind/buried vias. Decide the stub strategy before choosing the stackup.
- **Pads as stubs.**
  - Telian: enter a connector pad from the end opposite the solder leg, or a pad stub of about 50 mil results. At 25+ Gb/s, use SMT connectors.
  - TI: through-hole receptacles are entered from the bottom; SMT receptacles from the top with no vias [VERIFIED].
- **SerDes: 0 test points and 0 stubs.** VR rates this as a P0 "zero", not "minimise".

### 1.5 Crosstalk

- **Johnson's coupling model** ([P](https://www.sigcon.com/Pubs/news/2_13.htm)):
  - Worst-case NEXT: **K = 1/(1 + (D/H)²)**, where D is the centre-to-centre separation.
  - If 2·T_coupled < t_r, scale K down in proportion. D/H = 100 gives 80 dB.
  - Sum the aggressors: the two nearest neighbours, plus a little from the next two.
  - Differential pairs do not cancel aggressor coupling much ([P](https://www.sigcon.com/Pubs/news/3_20.htm)).
  - For extreme isolation, enclose the trace between same-voltage planes with a via row at about ¼" pitch.
- **Ott.** Crosstalk stays <2% at s = 4h for microstrip and s = 2h for stripline, and scales ∝ h² [VERIFIED].
- **Bogatin #20/#21.** A 2W gap gives about 2.5% NEXT; FEXT ≈ 0.5%·Len[in]/RT[ns] [S; **NOT RETR.**].
  - Cross-check: with w ≈ 2h, a 2W gap means D = 6h, and Johnson's formula gives K ≈ 2.7%. So the three rules agree, and Johnson's closed form is the one to encode.
- **Johnson's broadside data.** In a 20.5 mil cavity, moving traces from 6 to 4 mil above their planes (and from 7 to 5 mil wide) cut crosstalk from 220 to 143 mV at 13 mil pitch, and from 38 to 25 mV at 19 mil pitch: about 35% less.
- **Guard traces [VR CORRECTED].**
  - The source is **Bogatin & Simonovich** ([DesignCon 2013](https://www.signalintegrityjournal.com/ext/resources/article-images-2019/Guard-Traces---Love-Them-or-Leave-Them/4567Guard_Trace_DesignCon-2013-rev14_Final.pdf)). [HS] had a "−60 dB" figure from a snippet.
  - "−50 dB isolation is perfectly adequate and there is never a need for a guard trace" in most high-speed digital designs.
  - Microstrip guards: never.
  - Stripline guards: short both ends with the lowest-inductance via and match the coupled length. That gives −70 dB vs −50 dB.
  - λ/10 stitching was *tested* and showed "no benefit" in some cases. Only 3-D simulation quantifies guard performance.
  - Johnson: "the plane is the … best … guard trace". Guards help only on 2-layer analog boards, grounded at both ends ([P](https://www.sigcon.com/Pubs/news/15_02.htm)).
- **Ground fill on multilayer boards** has no function and modulates Z0 ([P](https://www.sigcon.com/Pubs/edn/GroundFill.htm)). Floating fill is an Ott red flag.
- **I/O coupling.** Fast nets near I/O nets drive common mode out on the cables (LearnEMC; also a HyperLynx rule).
- **Adjacent signal layers.** TI: route them "at a 90° offset" ([p.14](https://www.ti.com/lit/pdf/spraar7); VR FOUND). Ott pairs H/V layers on a shared plane. Analog/digital crossings should be at right angles [S].

### Implications for our system

- Build a **reference-layer map** (stackup plus fills) first. Express edge, void, crosstalk and stitching rules in units of **h**.
- Give every net a **t_r**: from IBIS, from the part family, or as an LLM estimate flagged as an assumption. t_r drives:
  - critical-length flags (t_r/6 and t_r/2);
  - stub limits, min(15 mil, 0.3/Gbps);
  - skew budgets;
  - the knee frequency, 1/(πt_r) or 0.5/t_r;
  - stitching pitch.
- Rank EMC findings by estimated V_cm or I_CM, not by violation count.
- Never auto-add terminations. Recommend slew control or a series R, and flag the net for SI review.
- Set spacing from a crosstalk budget, D ≥ H·√(1/K − 1). Never emit guard traces or fill by default.

---

## 2. Stackup selection

**Ott** ([Part 1](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-1.html) [P]):
- **Four factors:** number of layers; number and type of planes; layer order; spacing.
- **Layer-count drivers:** signal count and cost; frequency; Class A or B; enclosure; EMC expertise.
- **Five objectives:**
  1. Every signal layer adjacent to a plane.
  2. Signals tight to their planes.
  3. P/G tightly coupled.
  4. HS signals buried.
  5. Multiple ground planes.
- 8 layers is the fewest that meets all five. More layers are for routing only: "very little EMC advantage" above 8 [VR].
- 4 layers radiate 15 dB less than 2 layers. Go multilayer above 10–15 MHz.
- Plane-pair capacitance is inadequate below about 500 MHz, so on 4- and 6-layer boards favour signal-to-plane coupling over P/G coupling.
- Keep the stack symmetric (warp).

**Hartley** ([P](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley)):
- Never put two signal layers on one plane, or stack power planes with no ground nearby.
- Reject 1.6 mm S/P/G/S: the planes are about 1 mm apart, and every L1→L4 via forces a P↔G change. It is acceptable only with planes ≤ about 10 mil apart.
- S/P/S/S/G/S is "even worse".
- He disowns his own older stackup paper.

**Hubing:** no stackup guideline fits more than a small subset of boards. "Two ground planes above 25 MHz" is outdated ([P](https://learnemc.com/not-so-good-emc-design-guidelines); VERIFIED).

**Candidate library** (Ott [P], with Hartley annotations; VR verified Figs 3b, 6, 9 and 11):

| L | Stack | Objectives | Notes |
|---|---|---|---|
| 4 | S/G/P/S, signal–plane <0.010", core >0.040" | 1, 2 | At 0.005" spacing, ≥10 dB less loop radiation. Hartley: avoid at 1.6 mm with fast edges |
| 4 | G / S+P / S+P / G (power as a wide-trace grid; grounds stitched around the periphery) | 1, 2, 4, 5 | Ott: "best four-layer" [VR FOUND]. Outer grounds cut by pads |
| 4 | G/S/S/P | — | Shields the inner signals; hard to rework |
| 4 | S+P / G / G / S+P | 1, 2, 5 | Rework-friendly |
| 4 | S/S/G/S | 1 (L2 only) | Hartley's "worst" |
| 6 | S/S/G/P/S/S | — | Ott: "NOT to use" |
| 6 | LF/G/HF/HF/P/LF | 1, 2, 4 | Most common. Ott: OK with careful decoupling. Hartley: "even worse". **Warn with rationale; do not reject** |
| 6 | H1/G/V1/H2/P/V2 (5/5/40/5/5 mil) | 1, 2 | Orthogonal pairs share a plane |
| 6 | G/S/G/P/S/G | all 5 | Only two routing layers |
| 8 | LF/P/G/HF/HF/G/P/LF | all 5 | GND–GND via at each L4↔L5 change |
| 8 | G/H1/G/V1/H2/P/V2/G (10/5/5/20/5/5/10 mil) | all 5 | — |
| 8 | H1/G/V1/G/P/H2/G/V2 (6/6/15/6/15/6/6 mil) | 1, 2, 3, 5 | Tight P/G core; Ott's favourite |
| 8 | Six routing layers | — | "Definitely not recommended": use 10 |
| 10 | LF/G/HS/HS/P/G/HS/HS/G-or-P/LF | all 5 | Clocks on one HS pair, buses on the other |

**Other inputs:**
- **LearnEMC** ([P](https://learnemc.com/other-good-emc-design-guidelines)):
  - With ≥3 power pins on one voltage, use a plane pair <0.25 mm apart, with HF decaps on the side nearest it.
  - Keep power planes on one layer, never overlapping (balanced ±12 V excepted).
  - The gap between power planes must be ≥ the plane-to-ground spacing; VR adds ≥3 mm ("Maybe").
- **TI:**
  - "At least six layers"; adjacent signal layers at 90°.
  - HS pairs on top or bottom over GND: "**TI does not recommend stripline**".
  - VR: **CONTESTED** against Ott's objective 4. TI's motive is unexplained, possibly via stubs.
- **Ott's FR-4 rules of thumb:**
  - Microstrip Z0 is 60–70 Ω at w/h = 1 and 40–50 Ω at w/h = 2.
  - Stripline ≈ 0.6× microstrip; asymmetric stripline ≈ 0.75×.
  - Delay: 150 ps/in (microstrip), 180 ps/in (stripline).
  - Dk 4.0–5.0 (typically 4.5); Z0 ∝ 1/√εr.
  - u-blox: 50 Ω microstrip width ≈ 2× the dielectric thickness [VR].
- **Fibre weave:** rotate 10–35° or zig-zag, and prefer 1080/2116 over 7628 (TI). NXP: route off-axis ([SPRAAR7J p.3–5](https://www.ti.com/lit/pdf/spraar7); [AN10373](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/powerquicc/2284/2/philips_PCIe_pcb_routing_guide.pdf)).
- **Reference stacks:**
  - HDMI retimers: L1–L2 of 5–10 mil ([TMDS181](https://www.ti.com/lit/ds/symlink/tmds181.pdf)).
  - Espressif 4-layer: L2 is a complete GND with no signals.
  - OSH Park 4-layer: FR408HR, L1–L2 7.87 mil, 39 mil core.
- **JLCPCB:**
  - Dk 4.5 (2-layer), 7628 = 4.4, 3313 = 4.1, 2116 = 4.16.
  - Impedance ±10% (±5% on request).
  - Backdrill on 4–32 layers, ≥0.8 mm thick ([JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities)).
- **Johnson's EMC options instead of clock modulation:** planes; minimal trace-to-plane spacing; thin packages; slower edges; differential or low-swing clocks.

**Selection algorithm** ([HS] synthesis; no primary scoring function exists):
1. Estimate the routing layers needed. If ≥6, go to 10 layers.
2. From edge rates, emission class and enclosure, decide whether objective 4 applies.
3. Enumerate the library candidates.
4. Reject any candidate with an unreferenced signal layer, two fast layers on one plane, or adjacent power planes with no ground.
5. Score the rest: objectives met, minus forced P↔G changes, minus plane-pair separation when ≥3 power pins share a rail.
6. Minimise h, subject to a manufacturable width at Z0. Put the thickness in the core. Keep it symmetric.
7. Pair the orthogonal layers on a shared plane.
8. Field-solve per-layer width and gap, and emit net classes.

### Implications for our system

- **Choose the stackup before placement.** It fixes each layer's reference, which vias change reference, the stub lengths, and the width and gap per layer.
- Ship the library and the scorer. Record expert disagreements (Ott vs Hartley; TI vs Ott on stripline) as warnings with a selector: plane separation, edge rate, stub strategy.
- Keep fab stack options as data (HS did not research these). Use a field solver for impedance.

---

## 3. Differential pairs

**Physics (Johnson [P]):**
- **Each leg returns under itself.**
- **Skew creates common mode.** V_cm ≈ Δv·Δt/(2t_r), so a 20% skew gives 10% common mode, which dominates radiation and crosstalk ([CMA of Skew](https://www.sigcon.com/Pubs/edn/CMAofSkew.htm)). kicad-happy implements V_CM = V_diff·skew/(2T_rise).
- **Spacing.** In theory, 0.5 mm spacing gives about 40 dB of cancellation. In practice, drivers are rarely balanced better than 1:100, so "0.5 mm is close enough" ([P](https://www.sigcon.com/Pubs/edn/ReducingEMI.htm)).
- LearnEMC: an imbalanced pair radiates like a single-ended line.
- **Corner skew** ([Skewed Layout](https://www.sigcon.com/Pubs/edn/SkewedLayout.htm)):
  - Each corner adds 2p, 1.65p or 1.57p to the outer leg (square, chamfered or rounded; p = pitch). At p = 20 mil that is 5–6.4 ps. **Rounding does not remove skew.**
  - Budget layout skew to the driver's own skew, assumed ≥10% of t_r if unspecified. Examples: 100BASE-TX balanced to 1:1000 gives about 0.1"; 2.5 Gb/s with 200 ps edges gives about 20 ps.
  - Place ICs so a pair **exits the driver in the same direction it enters the receiver**, so turns cancel.
- **Serpentines** ([P](https://www.sigcon.com/Pubs/edn/serpentine.htm)):
  - At 8/8/5 mil geometry, NEXT ≈ 6%.
  - If a switchback's round trip is ≫ ⅓ t_r, it distorts the signal. If ≪ ⅓ t_r, it advances arrival by up to 2× NEXT per switchback (4× for a full serpentine).
  - The maximum coupled switchback is about 1" per ns of t_r.
  - Delay matching must also match configuration, width, Dk, loading, thresholds and terminations.
- **Differential vias (XFP):** an oval antipad with ground vias pinning the planes at each end, and no long stubs ([P](https://www.sigcon.com/Pubs/edn/XtkDiffViaGnds.htm)).

**Numeric rules (VR corrections applied):**

| Rule | Value | Source / status |
|---|---|---|
| Pair-to-pair spacing | ≥5W (6 mil trace → 30 mil) | TI SPRAAR7J [VERIFIED] |
| Pair to other nets | **≥30 mil to any signal; ≥50 mil to clocks or periodic signals; no other pair within 30 mil after escape** | [SPRAAR7J p.9–10](https://www.ti.com/lit/pdf/spraar7) [VR addition] |
| NXP pair to other nets | ≥max(20 mil, 4h); 30 mil from higher-voltage or faster-edge aggressors | [AN10373](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/powerquicc/2284/2/philips_PCIe_pcb_routing_guide.pdf) |
| Intra-pair skew | 5 mil for USB3/PCIe/SATA/HDMI; 50 mil for USB2 (AM57xx tables) | VERIFIED+CTX (device-family tables). MIPI CSI instead uses mode-conversion S-parameters, ≈ UI/50 |
| Where to compensate | Add length "near the location where the mismatch occurs" | NXP AN10373 [VERIFIED; AN10798 NOT RETR.]; TI |
| Jogs / serpentine spread | Jogs ≥15 mil (3W); maximum spread S1 < 2S | **VR: "amplitude ≥2W" NOT FOUND; the primary limit is a *maximum*** |
| Uncoupled length | **≤45 mil (1.14 mm)** into a pin or ball; breakout **within 0.25 in** | **VR CORRECTED** (the 3.0 mm value was from a forum) |
| Vias | Equal count on P and N, equally spaced, near the SoC. USB3 ≤2; USB2 ≤4; **PCIe/SATA/HDMI 0 on AM57xx/KeyStone II, 2 on AM64x/65x**; CSI 2 | VERIFIED+CTX / CORRECTED |
| Antipads | As large as possible (30 mil), on all layers; no non-functional pads | VR addition |
| In-line SMDs | ≤0603 (0402 preferred), symmetric. Void the plane 100% under pads, ≥2 layers deep; 60% under ESD/EMI pads | VERIFIED |
| Bends | >135° (TI Rev J replaces the older "two 45°"). NXP: ≥135°, ≥20 mil gap, flank segments ≥1.5W, equal left/right bends | VERIFIED (updated) |
| Constant width after escape; ≥1.5W from voids | — | SPRAAR7J |

**KiCad semantics** ([KiCad 9](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html) [P]):
- `skew` is measured against the **longest** matched net, not the average (corrected in HS).
- `within_diff_pairs` checks each pair separately.
- `diff_pair_gap` skips fanout; `diff_pair_uncoupled` counts non-parallel or out-of-gap length.
- Pair-to-pair clearance: `A.inDiffPair('*') && !AB.isCoupledDiffPair()`.
- kicad-happy's unverified protocol skew limits: USB HS 25 ps, PCIe 5 ps, Ethernet 50 ps, HDMI 20 ps.

### Implications for our system

- **Skew budget:** skew_max = min(spec/vendor value, 0.1·t_r), tighter for balanced links. Convert using the per-layer delay (KiCad 10 profiles; Ott's 150/180 ps/in).
- **Running-skew compensation:** walk both legs and insert a tune where |running skew| exceeds about 0.2 × budget. Checking end totals alone is not enough.
- **Placer:** add a cost for pair direction alignment.
- **Router:**
  - symmetric breakouts;
  - short or uncoupled switchbacks;
  - GND vias beside every differential via pair;
  - equal via counts;
  - `diff_pair_uncoupled` taken from NXP and TI values, not from forums.

---

## 4. Interface rule packs (vendor-keyed; conflicts flagged)

*All values are [P] unless tagged. TI table values are scoped to the named SoC family [VR].*

### 4.1 USB 2.0 / 3.x / USB4 / Type-C

| Param | Default | Variants / **conflicts** | Check |
|---|---|---|---|
| USB2 Z | 90 Ω ±15% diff, 45 Ω SE ([SLLA414A](https://www.ti.com/lit/pdf/slla414)) | Qualcomm 75–105 Ω; Microchip 90 +5/−10 Ω (Z0 40–55); AN13.10 SE 42–78 Ω | K class + solver |
| USB2 intra-pair | ≤1.27 mm / 50 mil ([SPRAAR7J](https://www.ti.com/lit/pdf/spraar7); [AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf)) | SPRAAR7A (2013) 2 mil; TUSB9261/SLLU149E 150 mil; [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb-2dot0-routing-constraints.html) 2 mm | K `skew within_diff_pairs` |
| USB2 length | Warn >150 mm (Microchip, "~6 in"); error >250 mm (Qualcomm) or >304.8 mm (TI Rev J, typ. 101.6 mm) | SPRAAR7A 4 in; SLLU149E "contact TI" beyond 8 in | K `length fromTo` |
| USB2 vias/stubs/TPs | ≤4 vias; 0 stubs; 0 TPs | Legacy: stub <200 mil | K / G |
| USB2 spacing | ≥30 mil to other nets, ≥50 mil to clocks | Microchip ≥3·max(W,H) (e.g. 24 mil, 66 mil); Qualcomm 3W; meanders ≤3X amplitude, ≥5X gap | K |
| USB2 reference | GND ≥5× pair gap each side; parts ≥5× away; no routing under parts ([AN13.10](https://ww1.microchip.com/downloads/en/Appnotes/AN13.10-Application-Note-DS00002972A.pdf)) | — | G |
| USB2 misc | No AC caps, no P/N swap, no branch to 2 connectors; short 1 kΩ stubs; PHY JTAG <6 in; SMPS away; TH entry from bottom; ≥0.5 mm around TH pins; remove unused pads | — | M/G |
| Shield | **Conflict → ask:** 330 Ω ∥ 0.1 µF (AN26.2); host-only ground with device AC-coupled (AN13.10); chassis strap + 10–50 Ω @ 100 MHz ferrite, optional VBUS 47–1000 Ω (SPRAAR7A) | — | ask |
| USB3 Z | 90 Ω ±15% | AN26.2 85 ±5 Ω; AM57xx 83.7–96.3 Ω; AM65xx 95 Ω ±5%; Qualcomm 70–100 Ω | K + S |
| USB3 intra-pair | 5 mil (SPRAAR7J, AN26.2, SLLU149E; SLLA414A: "15 ps/m, TI recommends 5 mils") | TUSB1046 2 mil; TUSB9261 2.5 mil; [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb3dot1-displayport-routing-constraints.html) 5 ps ≈ 0.7 mm (~6× looser; keep as the "physics-justified relaxed" option [D]) | K |
| USB3 inter-lane / AUX | 70 ps (10 mm) / 50 ps (7 mm) (Qualcomm) | — | K |
| USB3 loss | Connector→PHY: Gen1 ≤5.5 dB @ 2.5 GHz; Gen2 ≤7 dB @ 5 GHz (Qualcomm) | Heck: channel −6 to −20 dB, cable ≤7.5 dB | S |
| USB3 vias | ≤2 per trace, plus GND return vias | Heck ([DevCon](https://community.infineon.com/gfawx74859/attachments/gfawx74859/usb-superspeed-peripherals/18243/1/2-4_SSUSB_DevCon_DesignGuidelines_Heck.pdf), partly legible): ≈1 in of routing per via; ESD+CMC ≈ −1 in | K + G |
| USB3 length | 88.9 / 139.7 / 101.6 mm (AM57xx / KeyStone / AM65xx); TUSB7340 8 in | Heck: host 2–12 in, device 1–4 in (≤2 in) | K / S |
| USB3 spacing | 5W between pairs and to DP/DM; 30/50 mil (TI) | TUSB1046 3W; Qualcomm 4W (Gen2) / 3W (Gen1) RX–TX; Microchip 5X. If impossible: GND fill, or opposite sides of GND | K |
| USB3 AC cap | Qualcomm 75–265 nF (Gen2), 75–200 nF (Gen1); TI controllers 0.1 µF; redrivers 220 nF TX (+330 nF RX); TUSB1046 raised its DP max from 200 to 265 nF | — | M |
| AC-cap package/void | ≤0402 (0603 absolute; 0201 OK); no C-packs; symmetric; near the connector | **Void conflict:** 100% ≥2 layers (SLLA414A) vs 60% under ESD pads (SPRAAR7J) vs 100% under CMC/ESD (Heck) | M/G |
| Chain order | **connector → ESD → CMC → AC cap → PHY** (all sources) | Qualcomm: cap near the source or the connector; TUSB1002A: cap ≥0.25 in from the redriver [S] | G |
| Bends | ≥135°, balanced; one layer; TPs only in series, symmetric (TUSB1046) | — | K / G |
| USB4 | [S] only: 85 Ω ±7%; skew <3 mil; ~60 mm; budget 8.5 → 5.5 dB at 10G (Gen2 8.5 dB ≈ 5 in) | — | low confidence |
| Type-C CC | ≥8 mil (VCONN ≤600 mA); 200–600 pF total (220 pF 0201 X7R example); **no passives** between PD controller and receptacle [S] | TPS65988DK minimums: CC 8, VIN 6, GND 10, GPIO 4, cap GND 16 mil [S] | K/M |
| Type-C protection | TPD6S300A: at the connector; separate unprotected from protected; straight USB2/SBU with the largest radii; via *before* D1/D2 pins, not onto them; VBIAS 0.1 µF. Mux: connector → AC caps → redriver (TUSB1046). No numeric mux distance; CMC-before-mux disputed [S] | — | G |

### 4.2 PCIe Gen2–6

**TI SNLA426 loss budget (dB)** ([SNLA426](https://www.ti.com/lit/pdf/snla426)):

| Item | Gen3 | Gen4 | Gen5 |
|---|---|---|---|
| Package | 3.5 | 5 | 9 |
| 9 in high-loss board | 13 | 14 | 16 |
| CEM connector | 0.5 | 0.5 | 1.5 |
| 4 in add-in card | 6.5 | 8.5 | 9.5 |
| **Total** | **23.5** | **28** | **36** |

Further budget items:
- Crosstalk: negligible (Gen3), <2 dB (Gen4), 4–5 dB (Gen5).
- Gen5 temperature/humidity: 2–3 dB.
- Eye: 25 / 15±1.5 mV, 0.3 UI.

**Loss per inch at 8 / 16 GHz (TI SNLA426):**

| Material | Loss (8 / 16 GHz) |
|---|---|
| Megtron 6 | 0.189 / 0.336 dB |
| Rogers | 0.251 / 0.411 dB |
| GETEK | 0.548 / 1.017 dB |
| Nelco 4000-6 | 0.578 / 1.078 dB |
| FR4 (4.4/0.014) | 0.686 / 1.289 dB |
| Tetra-FR4 | 0.961 / 1.844 dB |

Other loss sources:
- [Efinix](https://www.efinixinc.com/docs/an063-high-speed-transceiver-design-guidelines-v1.2.pdf), at 6.25 GHz: ≈0.5 dB/in (M6) and ≈1 dB/in (FR4); RX maximum 25 dB.
- [EMA](https://www.ema-eda.com/wp-content/uploads/2025/10/PCIe-Design-Guide-Part-1.pdf) (EDA reseller, lower authority):
  - Budgets: Gen3 <20 dB @ 4 GHz; Gen4 <28 @ 8 GHz; Gen5 <36 @ 16 GHz; Gen6 <32 @ 32 GHz (PAM4).
  - Df: <0.010 / 0.005 / 0.002.
  - "12 in FR4 can exceed Gen5."
- NXP AN10373 (2005): 0.35–0.50 dB/in and 1–5 ps jitter per inch; add-in ≤4 in, system board <12 in.
- NXP AN12864: Gen4 1.0–1.2 dB/in [S].

| Param | Default | Variants / **conflicts** | Check |
|---|---|---|---|
| Zdiff | 85 Ω for CEM add-in (spec allows 70–100 Ω) | **TI SoC: 100 Ω ±10% (AM57xx/KeyStone), 95 Ω ±5% (AM64x/65x)** [VR]; SLLU149E 100 Ω / 50–55 Ω; REFCLK 100 Ω, ≤200 fs RJ | K + S |
| Intra-pair skew | ≤5 mil, **additive over segments** | Qualcomm 5 ps (0.7 mm); EMA ±2 mil (Gen4–6) | K per `fromTo` segment |
| Lane-to-lane | Not required (SNLA426 "typically up to 1 inch", but §13 says <6 in: inconsistent); Qualcomm: no REFCLK/TX/RX matching | SoC: RX/TX groups ≤550 mil, or 6 ns RX / 1.5 ns TX (AM65xx) | Emit on demand only |
| Single-board budget | Gen2 −6 dB @ 2.5 GHz / 250 mm; Gen3 −10 dB @ 4 GHz / 300 mm ([Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/PCIe%20layout%20guidelines.html)) | SLLU149E: Gen2 20 in FR4; Efinix add-in ≤101.6 mm; TI SoC 4700/5500/4000 mil | S |
| Via cost | ≈2 in per via (Gen2, FR4) | Heck: ≈1 in | Loss score |
| Via geometry | 10/20/40 mil drill/pad/antipad; via-in-pad; remove NFPs | EMA 8–10 / 18–22 / 30–35 mil | G |
| Return vias | ≤50 mil (TI Gen5) | ≥2 within 100–200 mil (EMA) | G |
| Stubs | <15 mil; Gen5 maximum ≈51–54 mil | 20 mil resonates at 8–16 GHz | G |
| AC-cap value | **Conflict:** TI 75–220 nF vs Gen3+ 176–265 nF (Qualcomm/Efinix/NXP); Gen2 75–200 (265); SLLU149E 0.1 µF 0402 | **220 nF fits all ranges**; BOM window 176–220 nF | M |
| AC-cap position | **Conflict:** near RX (SNLA426), near TX (SLLU149E), TX side (Efinix), either end (Qualcomm). All agree: at the connector for add-in/edge, never mid-line or staggered, pair caps side by side | "Within N mm of either endpoint" | G |
| Cap package/void | Smallest package (0201 pad is 12 mil vs a 5–7 mil trace); void 100%, 2 layers, larger than the pad | — | G |
| Edge/void/spacing | ≥max(5W, 5H) from the plane edge; ≥4H from voids; pairs 4–5H apart | Qualcomm 4W; EMA ≥3W (≥4W Gen6); Efinix ×5 | K/G |
| Serpentine | Segments ≥max(3W, 3H), at the source end | — | G |
| Edge fingers | No inner copper within 0.381 mm below the fingers; planes ≤2 mm into the footprint (Efinix / CEM 4.0) | — | G |
| Layer choice | **Conflict:** SPRAAR7J says no stripline; SNLA426/Efinix prefer coupled stripline or TX/RX on different layers at Gen4–5 | — | selector |
| Clock buffer (Renesas) | No parts or vias between the lines; 0402/0201; same layer and via count; "1 mm ⇒ 6 ps"; GND via at each change; ≥3W (5W optimal); one GND via per decap | — | G |

[D] L_max ≈ (budget − allowances) / (dB/in at Nyquist).
- Qualcomm's numbers imply about 0.85 dB/in @ 4 GHz and 0.6 @ 2.5 GHz.
- TI FR4 with the 14 dB Gen4 budget gives about 20 in before vias, realistically 9–12 in.
- **Store budgets and material tables, not mm.**

### 4.3 DDR3 / DDR4 / LPDDR4 (controller-keyed)

| Group | TI | Others | Check |
|---|---|---|---|
| DDR3 Z | 50 Ω ±5% SE; 100 Ω ±5% DQS/CK ([SPRABI1D](https://www.ti.com/lit/pdf/sprabi1)) | PolarFire 50/100 Ω | K |
| DDR3 ADDR/CMD fly-by | ±20 mil to CK **at each SDRAM**; equal vias per segment; stubs <80 mil; stub skew ±10 mil | [Micron TN-41-13](https://cdn.hackaday.io/files/19354828041536/tn4113_ddr3_point_to_point_design.pdf) ±1 mm; Intel ±20 ps [S]; PCBWay ±25 mil, stubs <200 mil [S] | K `skew` + `fromTo` per SDRAM |
| DDR3 CK | ±1 mil per SDRAM; stubs <40 mil; AC VTT termination at the end | — | K |
| DDR3 byte lane | DQS ±1 mil; DQ ±10 mil; ≤2 vias, equal; one layer; no mid vias; ODT only; bit swaps OK | Micron ±0.5 mm; Intel ±10 ps (FPGA deskew ≤20 ps) [S]; ISSI ±10 ps ≈ ±50 mil [S] | K + G |
| DDR3 spacing | ≥5W centre-to-centre, serpentines included (4W allowed only ≤1066 MT/s); stripline-equivalent length | — | K |
| DDR3 term / VREF / VTT | 39 Ω 1% (39–42) to VTT = 0.75 V at the last SDRAM, ≤500 mil. VREF ≥30 mil wide, ≥15 mil clear, top layer, GND-shielded, 0.01 + 0.1 µF per pin, ±1%. VTT regulator near the SDRAMs; VTT island; 0.1 µF per pin + 10–22 µF | — | G |
| DDR3 leveling | ≤2500 ps; DDR3-1333 example <2135 (or <1385) ps, >365 ps, at 180 ps/in | — | S |
| DDR4 CK/ADDR | A1+A2 ≤500 ps (skew ≤3); A3 ≤125 ps; AS 5–17 ps (1.3–3); AT ≤75 ps (≤14); CK P/N ≤0.4 ps per segment, ≤0.8 total; CK↔ADDR ≤4 ps per SDRAM; ≤3 vias (Δ ≤1); 4w/3w (2w within ≤500 mil of the ends); Rcp = Zo ±1 Ω, Rtt = Zo ±5 Ω; **no series termination** ([SPRAD06C](https://www.ti.com/lit/pdf/sprad06)) | [PolarFire](https://onlinedocs.microchip.com/oxy/GUID-FF8061A7-7A15-470F-A6F5-E733C24D85F0-en-US-11/GUID-07D00815-AB98-4174-B330-DAD67471AD0C.html) ≤1600 MT/s: **±100 ps**; R_T 30–50 Ω; ODT 80/120/240 Ω | K ps + `fromTo` |
| DDR4 data | BYTE ≤500 ps; DQS P/N ≤0.4 ps; **DQS↔DQ ≤2 ps**; ≤2 vias (Δ 0); **no cross-byte matching**; byte swaps OK, bit swaps only without CRC; 1 ps ≈ 5 mil | PolarFire **±25 ps** (training absorbs the rest); Agilex 5 ±3.5 ps, DQS–DQS <1 ps [S] | K |
| DDR4 VREF/VTT | VREFCA 20 mil + 0.1 µF per pin; VTT sub-plane at the bus end; VTT optional with one device, but CK termination still required | — | G |
| LPDDR4 CA | ≤450 ps (Dk 3.7–3.9); **CK P/N ≤0.75 ps**; ADDR vs CK ±312.5 ps die-to-pin; ≤3 vias; stub ≤20 mil; 5w/3w | — | K + G |
| LPDDR4 data | ≤450 ps; CK − DQS 0–3 tCK; DQS P/N ≤1.5 ps; DQS↔BYTE ≤150 ps; shortest DQ − DQS ≥ −49 ps; ≤2 vias; stub ≤40 mil | — | K |
| Policy | **Match to <20% of each limit in the tool; keep the limit as max; confirm with IBIS PVT** | Micron: ≈1% of the clock period (±1 mm addr / ±0.5 mm data @ 800 MHz; 6.5 ps/mm; outer layers ~10% faster; ≤20 ps per via; 10 ps = 1.5 mm) | Pack policy |

**Delay conversions disagree:**
- TI SPRAD06C: 1 ps = 5 mil.
- TI SPRABI1D: 180 ps/in.
- Micron: 6.5 ps/mm.
- Renesas: 1 mm = 6 ps.
- NXP: 6 mil/ps for packages [S].

Use the KiCad 10 stackup delay model instead of any one of these.

### 4.4 Ethernet 10/100/1000BASE-T and RGMII

| Param | Value | **Conflicts** / notes |
|---|---|---|
| MDI Z | 100 Ω ±10% ([SNLA387](https://www.ti.com/lit/pdf/snla387)) / ±15% ([Pulse](https://www.farnell.com/datasheets/2699973.pdf)); 50 Ω SE | Pairs <30 mil edge-to-edge lower Zdiff by up to 10 Ω (Pulse) |
| MDI length | TI: <2 in total | [AN2054](https://ww1.microchip.com/downloads/en/Appnotes/00002054A.pdf) / Pulse: <4 in |
| Skew | 20 mil (1G) / 50 mil (10/100) intra (TI); AN2054 <50 mil intra, <600 mil inter | Johnson: magnetics at 1:1000 balance → ≈0.1" budget |
| Vias | ≤2 per trace, matched; ideally none and no crossovers | — |
| Spacing | ≥30 mil between pairs (TI); TX–RX ≥50 mil, 100 preferred (Pulse); digital ≥300 mil (Microchip, Pulse) | — |
| **PHY↔magnetics** | **Pulse ≥25 mm "for EMI" vs Microchip <1 in (≤3 in max) vs TI MDI <2 in total**; TI forum: PHY→RJ45 ≲3 in [S] | Soft window: target ~25 mm, error >76 mm |
| Magnetics↔RJ45 | <1 in (all sources) | Hard |
| Edge | Pulse: PHY and TX pairs ≥25 mm from the edge (figure: 1 in, 2 in preferred; silicon 1–4 in from the connector); traces more than trace height from the edge | — |
| Voids | Void only under in-line parts: 2 layers (all layers for automotive), ~20 mil margin; no metal under magnetics (except integrated RJ45); AN2054 HV barrier from mid-magnetics to RJ45 | — |
| Bob Smith | 75 Ω + 1000 pF, ≥2 kV (TI) or 3 kV (Microchip; or 1500 pF/2 kV); ≥50 mil around the cap; not for PoE | — |
| Chassis | Keep-out ≥20 mil on all layers, bridged by cap + ≥1 MΩ (SNLA387), or 2× 1206 0 Ω swappable at EMC test (AN-1469, DP83867), or 2–3 1206 pads (AN2054); never overlap the planes | — |
| **ESD location** | **TI SNLA387: PHY side of the magnetics** vs generic: at the connector (SLVA680A) | Pack parameter |
| Misc | 49.9 Ω 1% + 0.1 µF near TD/RD; MII <6 in, matched within 2 in; 25 MHz crystal C_L1 ≈ 2C_L − 7 pF (start at 33 pF); no floating metal; ≥4 layers (6 recommended); bypass pad-to-via <10 mil | — |
| RGMII ([DP83867](https://www.ti.com/lit/ds/symlink/dp83867ir.pdf)) | 50 Ω; skew <11 ps (~60 mil); <2 in recommended, <6 in max | — |

### 4.5 HDMI, DisplayPort, MIPI D-PHY, SATA, UFS

| Interface | Values | Conflicts / notes |
|---|---|---|
| HDMI | 100 Ω ±15%; **no AC caps**; no swap; intra ≤0.15 Tbit, inter ≤0.20 Tchar (6 Gb/s ≈ 25 ps [D]). TI SoC: 90–110 Ω, ≤4000 mil, ≤5 mil, **0 vias**. Retimers: top layer, controls on the bottom. TPD12S016: ESD at the connector, no vias to the TVS, no 90° | ADV3003 inter ≤0.05 in [S]; Intel ±10%, ≤2 vias [S] |
| DisplayPort | 100 Ω ±10%; AC caps required; intra ≤20 ps (TI) | Qualcomm 5/70/50 ps (intra/inter/AUX). Caps 75–200 nF (DP 1.2) vs 75–265 nF (newer) |
| MIPI D-PHY ([Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/mipi-csi-d-phy-routing-constraints-up-to-2dot5-Gbps.html)) | 70–100 Ω / 36–52 Ω SE; intra 0.7 mm, inter 1.4 mm; spacing 2.5W others / 1W intra / 1–1.5W inter | TI AM62x: ≤10 in, 85–115 Ω, **loosely coupled** (LP mode), intra ≈ UI/50, lane ≤40 ps, ≤2 vias |
| D-PHY length vs rate | At 0.5 / 0.75 / 1.0 / 1.5 / 2.1 / 2.5 Gb/s: IL −2.1 / −2.3 / −2.3 / −2.5 / −3.5 / −6.5 dB; better cable 260 / 210 / 200 / 145 / 170 / 210 mm; worse cable 190 / 155 / 125 / 60 / 90 / 150 mm | Non-monotonic because of the assumed flex length → **`cable_il_db` input** |
| SATA | 100 Ω ±15%; ≤2.5 mil; caps ≤0402 near the connector; TX↔RX 5W; **P/N swap allowed** (TUSB9261) | SPRAAR7J: 85–115 Ω, ≤3500/5500 mil, ≤5 mil, 0 vias. Caps 0.3–12 nF (typ. 10 nF) [S]. LattePanda: no inversion, caps ≤10 mm [S] → controller-dependent |
| UFS (Qualcomm) | G3: −6 dB @ 3 GHz, 25/75/150 mm, 75–105 Ω. G4: −1.3 / −5.0 dB @ 2.9 / 5.8 GHz, ≤70 mm, 70–110 Ω. Intra 5 ps; lane–lane 30 ps (4.2 mm); RX–TX 1.5–3W | — |

UI-based budgets are stored as formulas and resolved to ps at the configured rate, then to mm via the per-layer delay.

### 4.6 CAN, RS-485, I2C, SD/SDIO, SPI/QSPI, slow clocks

| Bus | Rules |
|---|---|
| CAN ([SLLA270](https://www.ti.com/lit/pdf/slla270), [TCAN1042H](https://www.ti.com/lit/ds/symlink/tcan1042h.pdf)) | **Termination:** 120 Ω at the two ends only, or split 2× 60 Ω ±1% + 4.7 nF. It must survive node removal. **Bus:** 40 m @ 1 Mb/s, ≤30 nodes, stub ≤0.3 m. Length/rate pairs: 100/0.5, 200/0.25, 500/0.1, 1000/0.05; above 100 m, rate × length ≤ 50. **Stub** ≤⅓ of critical length (50 ns edge → 1.67 m; 160 ns → ~5.3 m). **Protection:** TVS, filter and CMC at the connector, *in the signal path*; ≥2 vias on protection grounds |
| RS-485 ([SLLA272D](https://www.ti.com/lit/pdf/slla272)) | 120 Ω at each end (2× 60 Ω low-pass when noisy). Stub L ≤ t_r·v·c/10 (1 Mb/s → 7 ft; 250 kb/s → 19 ft; 200 kb/s → 38 ft). Failsafe 2× 523 Ω at 5 V; 32 UL; length × rate <10⁷; lines close and equidistant |
| I2C ([SLVA689A](https://www.ti.com/lit/pdf/slva689)) | t_r ≤1000 / 300 / 120 ns; C_b ≤400 / 400 / 550 pF (Sm / Fm / Fm+). R_P ∈ [(VCC − 0.4)/3 mA, t_r/(0.8473·C_b)]. Fully automatable from stackup pF/mm + pins |
| SD ([Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/SDC2%20external%20SD%20card%20routing%20constraints.html)) | 50 MHz DDR / 100 MHz SDR: 10 pF, <150 mm, CLK↔data 6 mm. 208 MHz: 5 pF, <50 mm, 2 mm. Spacing 1.5W; CLK series R 18–27 Ω at the source |
| SDIO ([Espressif](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html)) | ±50 mil to CLK; ≤2000 mil; CLK GND-surrounded; 50 Ω ±10% |
| QSPI 133 MHz (Infineon AN240090) | ±30 / ±200 / ±1500 mil (IO, SCK–IO, …) [S, first pass] |
| Slow clock (Qualcomm SLEEP_CLK) | Star branches differ by <30 mm; daisy-chain stubs <7 mm |

On a PCB, the CAN and RS-485 stub limits matter only for daisy-chained connectors. The useful local checks are "termination only at end nodes" and "protection in the signal path". No primary TVS distance was found.

### 4.7 Clocks and crystals

| ID | Value | Source |
|---|---|---|
| XTAL-DMAX | ≤12 mm (½ in) from the oscillator pins, same side, load caps adjacent | [Microchip dsPIC33AK](https://onlinedocs.microchip.com/oxy/GUID-E48B4A26-F201-4F0A-BCBA-16461582816A-en-US-4/GUID-AA04B64F-3C38-4E1C-8B51-49DE3CFE2419.html) |
| XTAL-DMIN (vendor-specific) | ≥2.7 mm (ESP32) or ≥2.0 mm (ESP32-S3) from the clock pin; dense GND vias; **no vias on the clock traces** [VR] | [Espressif](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html) |
| XTAL-PAR | XIN–GND 1 pF, XOUT–GND 2 pF, XIN–XOUT 0.5 pF (AVR186); stray 2–5 pF (AN826); C_SHUNT 4.5 pF (TUSB9261); ~3.5 pF (AN-1469); 2–3 pF internal + 7 pF external = 9 pF (SWRA495L) | [AVR186](https://www.insidegadgets.com/wp-content/uploads/2013/02/Best-Practices-for-the-PCB-layout-of-oscillators.pdf); [AN826](https://ww1.microchip.com/downloads/en/AppNotes/00826a.pdf) |
| XTAL-SENS | 0.175 pF × 45 ppm/pF ≈ 7.8 ppm; LSE C_L ≥6 pF (7 pF typical); gain margin >5; PC13 toggling shifts LSE; Cs = pin + PCB | [ST AN2867](https://ecsxtal.com/store/pdf/stm32-microcontroller-application-note.pdf) [VERIFIED; no mm values] |
| XTAL-GUARD | Grounded ring or pour, no foreign nets inside or on the adjacent layer; tie to MCU GND; tie broken guards to a mirrored layer; nothing under the crystal on 2-layer boards; Espressif top-layer keep-out | Microchip; AN2867 ("essential"); SLAA322D; Espressif |
| XTAL-CAP | XIN cap first; C0G; short symmetric loop, cap grounds together; never route GND between the caps; keep cap grounds away from USB/RS-232/LIN/PWM/power returns; series R at the chip side | AVR186; [SLAA322D](https://www.ti.com/lit/pdf/slaa322); Espressif |
| XTAL-SEP/TP/MAG | XIN and XOUT apart; no test points; conformal coat for humidity; no magnetics nearby; no HS traces near crystals, oscillators, SMPS, magnetics or mounting holes | AN2867; Espressif; SPRAAR7J |
| **XTAL-CAN** | **Conflict:** ST says do not tie the can to oscillator GND; TI and AVR say tie it to ground; TUSB9261 says VSSOSC must not touch the plane | vendor switch |
| **Copper under** | **Conflict:** solid ground (most sources, plus Nordic) vs cut planes (TI CDCE925 [S]). Ground for an MCU Pierce; cut only if the datasheet says so | — |
| Other | Clock vias surrounded by a C-shaped GND ring (Qualcomm); clock driver beside its oscillator (LearnEMC); emcvisual: crystal ≥5 mm from the edge and ≥10 mm from cable connectors (citing AP24026/AN2867) | — |

No primary source gives a crystal-to-switch-node distance. [IF]'s 3 mm keep-out is [D], and ≤5 mm is a heuristic [VR].

### 4.8 Switching-regulator pack (IF §8; overlaps the power digest)

- **MPS** ([AN065](https://media.monolithicpower.com/document/PCB_Layout_Design_Guidelines_for_NB67xSeries.pdf)):
  - **Cin <2 mm** from the chip. This is the only numeric primary Cin value.
  - VCC cap <2 mm, on the same layer.
  - AGND–PGND tie with ≥2 vias; 4 vias VCC→AGND and 8 to PGND.
  - 10/20 mil VIN/PGND vias, with >20 between the input caps.
  - FB divider at the pin, with no vias.
  - Inner1 = PGND.
- **Rohm** ([60AN066E](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf)):
  - CBYPASS 0.1–0.47 µF on the top layer; bulk Cin can be about 2 cm away; "even 1 mm" of shortening matters.
  - **Cin and Cout grounds 1–2 cm apart.**
  - 0.3 mm thermal vias at about 1.2 mm pitch.
  - Copper width >1 mm/A (1 oz) or >0.7 mm/A (2 oz).
  - Via L ≈ (h/5)(ln(4h/d) + 1) nH.
- **Loop anchors:**
  - [SNVA803](https://www.ti.com/lit/pdf/snva803): a 20 mm² lateral loop is >1 nH; a 2 mm² vertical loop is <0.5 nH, with about 4 V less overshoot.
  - [EPC](https://epc-co.com/epc/documents/papers/Optimizing%20PCB%20Layout%20with%20eGaN%20FETs.pdf): going from 0.4 to 2.9 nH costs >4% efficiency; overshoot is 100% at 1.6 nH vs 30% at 0.4 nH.
  - [SLYT682](https://www.ti.com/lit/pdf/slyt682): 5 A/ns × 2 nH = 10 V; use a 5 mil L2 shield; top-layer keep-out under the inductor.
  - AN-139: 187 nH single-layer vs 13 nH at 0.12 mm (>3× better than a 1.5 mm 2-layer board).
- **Other TI guidance:**
  - SLYT614: Cin → L → Cout → small-signal; 1 via per amp.
  - LM10504: SW trace ≤100 mil.
  - SLVA773: FB not parallel to SW.
  - LM5163: shield FB on another layer if R_FB >100 kΩ [S].
- **Conflicts:**
  - Cin/Cout grounds: Rohm vs TI/MPS.
  - Copper under the inductor: Rohm vs TI (VR CONTESTED).
- **Loop-area tiers [D]:** ≤2 / ≤10 [S] / >20 mm². VR: there is no primary pass/fail limit, so treat these as soft.

### 4.9 Fab, assembly and mounting-hole profile (IF §10)

| Parameter | JLC 2L (rec/abs) | JLC multilayer | PCBWay | OSH Park 2L / 4L |
|---|---|---|---|---|
| Trace/space (1 oz) | 0.10/0.10 | 0.09/0.09 (3 mil in BGA fan-out) | 0.10/0.10 | 0.152 / 0.127 |
| Drill | 0.2 pref / 0.15 | same | 0.15 (≥0.2 avoids surcharge) | 0.254 |
| Annular ring | 0.25 / 0.18 | 0.20 / 0.15 | 0.15 | 0.127 / 0.102 |
| Copper to edge | 0.2 routed, **0.4 V-cut** [VR] | same | 0.20–0.25 | 0.381 |
| Silk | ≥0.15 line, **≥1.0 mm text** [VR CORRECTED], 0.15 pad-to-silk | same | 0.15 / 0.8 mm | 0.127 |

JLC details ([JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities)):
- Via 0.15/0.25 mm.
- Hole-to-hole: 0.2 mm (via), 0.45 mm (pad).
- PTH-to-track: 0.28 mm (0.35 mm recommended).
- Mask bridge: 0.10 / 0.13 mm.
- SMT panel: 5 mm rails, 2 mm tooling holes, 1 mm fiducials at 3.85 mm.
- Minimum pitch: 0.35 / 0.40 mm.

Other fabs and mounting holes:
- Eurocircuits: IPI = IAR + 0.075 mm (≥0.200 mm); NPTH ring ≥0.30 mm.
- RP2040 mounting holes: "NPTH FD2.75 SM3.15 **KO6mm**" ([RPi](https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf)); other Pi boards use KO 6.2 mm.
- M3 clearance holes: 3.2/3.4/3.6 mm [S]. Keep HS traces away from mounting holes (TI).
- Keep-out Ø = max(head/standoff + 2×0.5 mm, vendor example).

Fab packs set `min` only (precedence 10). Interface packs set `opt`/`max` and never relax a fab minimum.

### 4.10 Vendor-spread summary

| Quantity | Tightest | Loosest | Ratio |
|---|---|---|---|
| USB3 intra-pair | 2 mil (TUSB1046) | 0.7 mm (Qualcomm) | ~14× |
| USB2 intra-pair | 2 mil (SPRAAR7A, 2013) | 150 mil (TUSB9261) | 75× (historic) |
| DDR4 DQ↔DQS | 2 ps (TI) | 25 ps (PolarFire) | 12.5× |
| DDR4 ADDR↔CK | 4 ps (TI) | 100 ps (PolarFire) | 25× |
| Ethernet PHY↔magnetics | <1 in (Microchip) | ≥25 mm (Pulse) | opposite directions |
| PCIe AC cap | 75–220 nF (TI) | 176–265 nF (Qualcomm) | 220 nF fits both |

### Implications for our system

- Key every pack by vendor profile. When the vendor is unknown, use the tightest [P] value plus an `info` finding listing the alternatives.
- **Store physics budgets, not mm:**
  - dB budgets and per-material dB/in tables;
  - via penalties (≈1–2 in each);
  - ESD+CMC penalty (≈1 in);
  - UI formulas and a cable-loss input.
  
  Then compute L_max for each stackup.
- **Delay packs** emit ps rules with `opt` = 20% of the limit and `max` = the limit. DDR fly-by needs one `fromTo` rule per SDRAM per group.
- Packs supply placement intents:
  - chain order;
  - distance windows (crystal annulus, Ethernet ~25 mm);
  - end-node termination;
  - AC cap at either endpoint.

---

## 5. EMC placement: connector zoning, protection, stitching, edges

**Zoning** (LearnEMC [P]; VR VERIFIED, with numeric defaults):
- Cabled connectors on **one edge or one corner**.
- **No high-speed circuitry between connectors** (Guideline #3, "one of the most common problems"); otherwise bond the chassis at both connectors.
- I/O device within **~2 cm** of its connector; one connector per device's off-board links.
- Non-I/O parts **≥2 cm** from I/O. The 2 cm is "not necessarily the best advice in every situation".
- No unrelated traces between a connector and its device; no HF signals under I/O parts.
- Clock driver beside its oscillator; exclusive communicators together.
- Minimise vias on HF nets; tie unused inputs.
- **Worst guideline:** "group by type, HS farthest from the connector". Instead, put each connector's talkers nearest it.

**I/O nets and filters** (LearnEMC [P]):
- I/O nets end in a series or filter part near the connector.
- An IC that drives a cable directly must not inject more than ~1 mV of common mode.
- Filters need minimal parasitics, and no ringing higher-order designs.
- CMCs go only on **balanced** pairs. **Never put a ferrite on ground.**
- IC-protection devices ground to that IC's ground; board-protection devices ground to the EMC ground.
- Route ESD current to a metal enclosure without pulling it onto the board. With plastic enclosures, check seam arc paths and slow high-impedance inputs with resistors.
- Treat every pin of a fast IC as an HF source: DRAM supply pins carry more harmonic current than signal pins.

**TVS topology** ([SLVA680A](https://www.ti.com/lit/pdf/slva680) [P]; VR: topology VERIFIED, mm distance NOT FOUND):
- Place the TVS "as near to the connector as design rules allow".
- Place the IC "much further from the TVS than the TVS is to the connector".
- No stubs. No via between the source and the TVS.
  - If a via is unavoidable, go source → TVS → via (Case 1).
  - Avoid Case 2 (a branch to the IC before the via).
- **0.25 nH adds 10 V** at 8 kV (dI/dt = 4×10¹⁰ A/s).
- A 90° corner develops ≥7 kV and arcs below a **2.6 mm** radius. Use curves, ≤45° at most, and treat the region as a keep-out for unprotected traces.
- **TVS ground:** one via **immediately adjacent** to the ground pin, into a same-layer plane coupled to an adjacent plane.
  - Example: 4 stitching vias plus a chassis screw.
  - BGA-TVS via: 0.254 mm pad, 0.152 mm drill, filled and capped, 0.1 mm clearance.
  - Make the via as large as possible.
- The 5–10 mm limit is a blog heuristic, so treat it as soft.
- emcvisual flags a diode nearer the IC than the connector, or one with no ground pour or via within 2 mm.

**CMCs and filters:**
- TPS case study: a choke more than 30 mm away failed CISPR 25; it passed **within 5 mm** of the DC connector ([TPS](https://tps-elektronik.com/en/case-studies/how-to-pass-automotive-conducted-emissions-cispr-25-class-5-with-tps-split-ground-plane-and-common-mode-choke-placement-emc-layout-guidelines-for-automotive-dc-dc-converters/); VERIFIED case study).
- TI: AC caps on the protected side of the CMF; 0402 0 Ω no-stuff alternative to the CMF.
- emcvisual: flag filter parts more than 10 mm from the pin.

**Edges** (VR closed this gap):
- TI: **≥90 mil** from the reference-plane edge.
- LearnEMC: **≥2X** from the board edge, where X = trace-to-return height.
- u-blox: **>3W** from the GND edge.
- Also:
  - TI Gen5: 5·max(W, H).
  - Microchip: SS ≥5W from plane edges and splits; terminate narrow floods with vias.
  - Pulse: more than the trace height; Ethernet ≥25 mm.
  - [HS]: centreline ≥ w/2 + 3h.
- Checker thresholds: kicad-happy < h; EMI Guardian 1 mm; emcvisual <3h (≥1 mm) over ≥3 mm.
- A copper guard band along the edge was the best fix for edge-driven common mode [S].
- **Plane edges are zone-boundary checks.** KiCad's `edge_clearance` covers only Edge.Cuts.

**Stitching** (CONTESTED, per VR):
- Ott stitches the G/S/S/G periphery as a Faraday cage.
- LearnEMC: perimeter vias every 2 cm are not-so-good. They are usually unnecessary, and a perimeter-only ring "will create a resonant cavity", so distribute vias instead.
- **No primary source gives λ/20 or 3–5 mm pitch.** λ/20 comes from Ott's *aperture* red flag (6" at 100 MHz).
- TPS: stitch split boundaries every **10–15 mm**. The original 40–50 mm failed; 12 mm fixed it ("above 100 MHz the slot … acts as an effective antenna"; medium authority, soft).
- Johnson: a ¼" via row for isolation, and the 10:1 via ratio.
- u-blox: a stitched GND ring at the edge, with power planes kept back.
- KiCad master stitch default: max(2 mm, 2× via).

**Grounding and chassis:**
- **One ground.** Hubing 2019 calls "more than one ground" MOST EGREGIOUS ([slides](https://r6.ieee.org/scv-emcs/wp-content/uploads/sites/111/022019ToddHubing.pdf)).
  - Clearing ground under magnetics, inverters or HV is fine; gapping it is not.
- **Chassis bonding:** use an overlapping chassis layer bonded with multiple SMT caps, plus one LF tie. Never a single point at the I/O by default, and never at the oscillator.
  - "Bond (at RF) everything that leaves the board"; near metal, "Connect to it!"
- **Mixed signal (Ott):** one plane, partitioned, with routing discipline on all layers.
  - LSB at 1 V: 8-bit 4 mV, 10-bit 1 mV, 12-bit 240 µV, 14-bit 60 µV, 16-bit 15 µV.
  - At ≥14 bits, use isolated regions solidly joined under each ADC, with no trace crossing the slots on any layer.
  - Test: split with 0 Ω jumpers every ½" and compare.
- MT-031: >300 mV between planes risks latch-up. Check this only when a split is deliberate.
- DA9080 mandates GND cuts between bucks, so a datasheet override must exist [VR].

**Pre-compliance:**
- **LearnEMC's 10-step review.** Hold it before layout and again at the first draft:
  1. Ground structure and I/O.
  2. Plane extent, no gaps.
  3. Remove ground traces and fills.
  4. Power on a <0.25 mm plane pair.
  5. I/O nets.
  6. Filters.
  7. Transition times.
  8. Critical components (op-amp loops over the plane, PLL ferrites, no ferrite on ground).
  9. Inverters.
  10. Each test's current path (CE, RE, BCI, RI, EFT, ESD).
- Include **footprints for optional filters, TVS and shields**.
- "Blindly adhering" to rule lists fails; identify sources, victims and paths ([LearnEMC](https://learnemc.com/effective-application-of-emc-design-guidelines)).
- **Johnson:** EMI is too complex for simulators; good tools are "more like expert systems". A 2× faster design needs 6 dB more margin. Scan early.
- **Ott:** clamp every cable.
- **Hubing's 7 common errors:**
  1. Blindly following guidelines.
  2. Uncontrolled transition times.
  3. Not following currents.
  4. Missing the critical traces.
  5. More than one ground.
  6. Bad decoupling.
  7. Bypassing filters.

**Ott's red flags** ([P](https://hott.shielddigitaldesign.com/techtips/red_flags.html)):
- edges <10% of the period;
- apertures >λ/20;
- split grounds;
- traces over slots;
- pigtails;
- non-contacting backshells;
- painted seams;
- unreferenced signal layers;
- multiple-value parallel decaps;
- ungrounded fill or thieving;
- unshielded, unfiltered cables;
- a single-point chassis bond.

His satirical **"maximize emission" list**, inverted, is worth 20–30 dB ([P](https://hott.shielddigitaldesign.com/techtips/maxemission.html)).

**emcvisual thresholds** [P-code]:
- crystal ≥5 mm from the edge and ≥10 mm from connectors;
- inductor ≥3 mm from the edge and ≥10 mm from connectors;
- switch node <100 mm² (<40 mm² near an edge or connector);
- hot loop flagged at 30–40 mm².

**Placement priority** ([HS] §8):
1. Lock mechanicals; cluster connectors; mark the I/O zone.
2. Protection, filters, CMC, magnetics and the chassis bond at the pins.
3. Interface ICs within ~2 cm, with a clear corridor.
4. Critical ICs (SoC, fly-by DRAM, SerDes) with short, uncrossed, direction-aligned links, never between connectors.
5. Clocks next to their consumer, away from I/O and edges.
6. Partition by function over one plane; power stages away from I/O.
7. In-line SI parts (series R at the driver, AC caps), then decaps.

Steps 1–3 are hard anchor-relative constraints. Steps 4–6 are soft costs; no primary source gives weights.

### Implications for our system

- **Placer costs:**
  - MREMC V_cm "between connectors";
  - I/O-zone intrusion;
  - fast-net length and crossings;
  - pair direction alignment;
  - crystal, inductor and switch-node distance to edges and connectors.
- **TVS and CMC are comparative constraints:** d(TVS, connector) < d(TVS, IC); zero vias before the TVS; GND via at the pad.
- **Edges, per layer:** ≥2h to the board edge (`edge_clearance`), plus ≥90 mil or w/2 + 3h to the plane edge (geometric).
- **Stitching:** use a single "largest unstitched region" metric, so the perimeter-vs-distributed debate doesn't need resolving.
- **Optional footprints:** always add them (CMF 0 Ω, TVS, shield-can pads, chassis R/C) when compliance is uncertain.

---

## 6. Myths and context-dependent rules (encode as negative rules carrying the physics replacement)

| Slogan | Verdict | Status |
|---|---|---|
| 90° corners | Negligible up to ~2 Gb/s: ≈1 ps, 0.012 pF, ≈0.3% at 100 ps. Rounding removes 21% of the corner copper; 70–90% would be needed. Corners start to matter around 10 Gb/s and for pair skew. The myth traces to the MECL handbook (1971); 3 Ω at ~80 GHz; a 5 mil corner is 8.5 fF, with no impact below ~70 GHz | VERIFIED+CTX. **Exceptions:** ESD paths ≤45° (2.6 mm arc); RF uses arcs or 135° ([Johnson](https://www.sigcon.com/Pubs/edn/bigbadbend.htm); [Altium](https://resources.altium.com/p/slaying-900-right-angle-bend-dragon)) |
| 20-H | Shim & Hubing: "slightly higher" far field (3.6 dB NOT RETR.). LearnEMC: helps only when power is sandwiched between grounds; 2–3H is enough. **Montrose 2005 FDTD: "fact, not fiction"; 10-H may suffice, but only on high-density multilayer boards with multiple planes, and parts negate the effect** | **CONTESTED** → selector ([Montrose](https://courseware.zcu.cz/CoursewarePortlets2/DownloadDokumentu?id=186283)) |
| Split A/D ground | Only for <100 kHz isolation at ~1000:1 sensitivity, and better done as a separate-layer return | VERIFIED+CTX (≥14-bit exception) |
| I/O ground island with a single-point tie | "One of the worst" | LearnEMC; Ott |
| Group by type, HS far from the connector | "More crazy layouts than any other" | LearnEMC |
| 3W rule | Proxy for D/H; use Johnson's K | Johnson; Ott |
| Guard traces | Stripline only, end-shorted and length-matched | **CORRECTED** |
| Ground fill on multilayer | No function; perturbs Z0. Floating fill is a red flag | Johnson; Ott |
| Perimeter vias every 2 cm | Usually unnecessary, can create a cavity → distribute | CONTESTED (Ott's G/S/S/G) |
| Two ground planes above 25 MHz | Outdated | VERIFIED |
| Terminate beyond λ/4; series R above 1 V/ns; Z ≥ Z0/4 | Not criteria; compare delay to t_r | LearnEMC |
| Single-point at LF / multipoint at HF | Misused. At LF, limit the options; at HF, give one good path | LearnEMC |
| Minimise all HS lengths | Not an EMC fix ("control loop areas"). Guideline-followers do worse than designers with no guidance | VERIFIED |
| Rely on slow logic | Parts speed up over production life → use slew control | VERIFIED |
| Ferrite on ground | Never | LearnEMC |
| 0.1 µF up to 15 MHz / 0.01 µF above; 1 ground per 8 lines | Too narrow | VERIFIED |
| Decaps across a plane gap | "Don't gap the ground plane!" | LearnEMC |
| Ground daughterboards to chassis | Returns belong on connector pins | LearnEMC |
| Rounded corners fix pair skew | No (1.57p–2p) | Johnson |
| Tighter coupling always reduces EMI | Not below ~0.5 mm | Johnson |
| Follow as many guidelines as possible | 90% compliance can be worse than following 1–2 | LearnEMC |
| More anti-rules | "Power traces ≥3× signal width"; ground islands under ICs; "daisy chain, no stubs" ("sometimes"); "ground E-shields at ≥2 points" ("terrible") | [VR] |

### Implications for our system

- **Myth rows become negative rules.** Each one blocks the LLM from emitting the slogan and links to the physics check that replaces it.
- **Corner-angle rule scope:** only net classes `ESD_UNPROTECTED` and `RF50`.

---

## 7. Hard vs soft vs explicit-selection rules ([VR] §3)

| Class | Rules | Encoding |
|---|---|---|
| **Hard: fab/assembly** | Fab absolute minimums (router targets the recommended values); no courtyard overlap; IPC-2221B as a floor; JLC silk 1.0 / 0.15 mm | Board setup + `.kicad_dru` |
| **Hard: topology** (all primary sources agree) | No split or void crossings; ≥1.5W from voids (except voided SMD pads); crossings over the bridge; connector→TVS→IC with no stub, no via before the TVS, and a GND via at its pad; 0 TPs and stubs on SerDes. Power/RF: CIN on the IC layer with 0 hot-loop vias; FB from the COUT pad; a single "mandatory" AGND–PGND tie; shunt cap through the named VSS pin; antenna keep-out polygon; no digital under RF; AGND+DGND to the analog plane | G-checker → reject |
| **Hard within scope** | Pair skew, via count, 30/50 mil keep-outs, via stub min(15 mil, 0.3/Gbps) | Only when the interface and rate are known; carries `source_scope` |
| **Soft, strong** | Return via ≤200 mil as a hard max, "closer is better" as the objective; ≥90 mil from the plane edge / ≥2h from the board edge; one-edge connectors; I/O ≤2 cm, non-I/O ≥2 cm. Power: L2 ≤0.13 mm; 1 via/A; C_boot ≥10·Cg; bead ≤20% of rated current; EP vias 0.3 mm at 1.0–1.2 mm | High-weight costs; warnings quoting the source |
| **Soft, weak** | TVS ≤5–10 mm; CMC ≤5 mm; crystal ≤5 mm; CIN ≤0.5–1 mm (MPS ≤2 mm); FB ≤2–3 mm; RF↔SMPS 20 mm; stitching λ/20, 3–5 mm, or 2 mm near SerDes; **2W/3W/5W multipliers (compute crosstalk in h instead)**; 2 cm²/W | Rank objectives ("closer than any other part"); never DRC |
| **Context switch** | 20-H; copper under inductors; CIN/COUT grounds; **microstrip vs stripline**; thermal-via tenting; guard traces; "smallest cap closest"; perimeter stitching; PMIC ground cuts; **termination at t_r/2 vs t_r/6** | Store both with a selector (power, layers, rate, fab, datasheet); ask; log |
| **Myth exceptions** | 90° corners matter on ESD and RF nets | Net-class scoped |

**Recalibrations (VR):**
- TL-5 (SerDes test points) becomes hard.
- The EMI-7 mm limit becomes soft; its topology stays P0.
- The EMI-6 10–15 mm pitch is soft. The P0 rule is "no crossing without a bridge or stitch".
- RF-05 splits into a hard PCB keep-out plus an enclosure clearance in the mechanical checklist (15 mm for ESP32).

**Schema additions:**
- `source_scope`;
- `statement_strength`: mandatory / must / should / as close as possible / good guideline;
- `contested_by`.

**The LLM's value-add:** converting relative language into **comparative constraints** (distance ratios, rank orders), not invented millimetre values.

### Implications for our system

- Output three tiers:
  1. DRC errors (hard rules).
  2. Scored warnings (soft rules).
  3. User decisions (context switches, logged with rationale).
- [D] heuristics default to warning until calibrated against vendor evaluation-board layouts.

---

## 8. Encodability: KiCad native vs custom geometric checkers vs simulation

**KiCad 9/10 native constraints:**
- Geometry: `track_width`, `clearance`, `diff_pair_gap`, `diff_pair_uncoupled`, `edge_clearance`, `track_angle`, `track_segment_length`, `physical_clearance`.
- Length and timing: `skew` (measured vs the longest net; `within_diff_pairs` option), `length` (also the tuner target), `via_count`.
- Holes, vias and silkscreen: `hole_size`, `annular_width`, `hole_to_hole`, `via_diameter`, `silk_clearance`, `courtyard_clearance`, `text_height` and `text_thickness`.
- Other: `assertion`, `disallow`.

**Rule conditions:** `hasNetclass`, `inDiffPair`, `isCoupledDiffPair`, `intersectsArea`, `intersectsCourtyard` and `memberOfSheet(OrChildren)` (9.0.2). KiCad 10 adds **`fromTo('U1-A*','U2-B*')`**.

**KiCad 10 time domain** ([docs](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html)):
- Delay = Σ length × per-layer unit delay + via delay (stackup height × via unit delay, with per-layer-pair overrides) + pad-to-die.
- Tuning profiles hold the ps targets. They are recommended for DDR/PCIe/USB even on one layer.
- ps and mm cannot be mixed in one constraint.
- Backdrill is modelled on vias and pads, from one or both sides, with a "must-cut" layer.

**KiCad master (post-10)** ([keywords](https://gitlab.com/kicad/code/kicad/-/raw/master/common/drc_rules.keywords) [P-code]): `return_path`, `stub_length`, `net_chain_length`, `hole_aspect_ratio`, `microvia_stack_depth`, `net`.
- **`return_path (layer "B.Cu") (net "GND")`**:
  1. Union the zone fills on the reference layer.
  2. Subtract that union from each track polygon of the net chain.
  3. Report any remainder as unreferenced.
  4. Merge adjacent findings with union-find.
  
  It checks one explicit layer only. It does not check vias, detours, edges or reference changes.
- **Net chains** bridge series components. Their topology gives the trunk plus each stub's branch point, length and delay.
- **`PCB_VIA_STITCH`**:
  - Modes: STITCH and GUARD. Layouts: PLAIN, STAGGERED and POISSON. Default pitch is max(2 mm, 2× via).
  - Exposed over IPC (`ViaStitchGuardSettings`), with a DRC check for overlapping zones.
- The syntax may change before KiCad 11. Whether `A.NetChain` conditions will exist is unknown.

**IPC API (kipy, MIT):**
- Available calls: `get_stackup`, `get_zones`, `refill_zones`, `get_pad_shapes_as_polygons`, `hit_test`, `Zone.filled_polygons`.
- SWIG does not expose the stackup, so parse it from `.kicad_pcb`.
- KiCad 10 IPC cannot make persistent custom DRC markers. Report through an HTML/JSON overlay, with selection and zoom.

**Custom checker specifications** ([HS] §11, plus [IF] geometric functions):

**A. Reference map.**
1. Read the stackup.
2. For each signal layer, record both neighbours, h_up and h_down, and whether each is filled with GND or a declared reference net.
3. Take the nearer filled plane as the reference. For stripline, keep both (≈75% returns on the nearer).
4. Refill zones first. Lint Ott's objective 1 at this stage.

**B. Return continuity.**
- Fast path: master `return_path`.
- Full path:
  1. Sample the trace against a net-labelled raster or polygon map.
  2. Compute the geodesic detour from entry to exit (A* on the raster, or a visibility graph).
  3. Classify each break as VOID, ISLAND or SPLIT.
- **Merge antipads into voids first.**
- Buffer the trace by 1.5W, or by w/2 + 3h.
- Severity scales with t_r and with detour/h.

**C. Reference changes.**
1. At each via or PTH pad, find the layers actually used: track endpoints within the pad radius, plus SMD pads hit.
2. Map each used layer to its reference set. If the set is unchanged, the via is OK (Ott case 2).
3. Same net on different planes: find the nearest via spanning both planes. The extra loop is ≈ d × plane separation; flag above ≤200 mil, preferably 1–2 mm, scaled by data rate.
4. Different nets: find the best-loop capacitor, warn of 5–10 nH, and suggest re-layering.

**D. Loop area.**
- A = Σ length·h + detour area (shoelace) + Σ d_via·Δz.
- Screen with E = 2.632×10⁻¹⁴f²AI/r up to the knee, with I = V/Z0.
- Use this for ranking only: the cable common-mode path usually dominates.

**E. Crosstalk.**
1. Spatially hash the segments.
2. Pair segments within ≤5° of parallel; D = s + (w1 + w2)/2. Include broadside pairs on adjacent layers.
3. Coupling: K × min(1, 2T/t_r), plus microstrip FEXT ∝ L/t_r.
4. Per victim, sum the two nearest aggressors plus the next two. Use stricter budgets for I/O and analog victims.

EMI Guardian's (h/s)² proxy is a cruder version of the same idea.

**F. Connectors.**
1. Take each connector's reference point as the centroid of its ground/shield pins.
2. Score whether all connectors sit in one edge band or corner.
3. For each fast net, classify which side of the net each connector is on.
4. Run MREMC: L_ret → V_cm → E_max.
5. Flag E_max within 6 dB of the limit, or V_cm >1 mV (100 µV for strict limits).

Use this both as a placement cost and as a post-route check.

**G. Stitching.**
1. Clip the GND vias spanning a plane pair to the overlap of both fills.
2. Find the **largest empty circle** (Voronoi), diameter d_max.
3. Require c/(2√εr·d_max) > f_knee. For apertures and fences, require d_max ≤ λ/20.
4. Prefer distributed stitching.
5. For GUARD fences, measure the maximum gap along the offset polyline. The master generator can create fences.

**H. Via stubs.**
1. Get z-depths from the stackup.
2. Take the drilled span minus any backdrill, and the used span from the attached tracks.
3. Stub = barrel beyond the used span + pad rings + unremoved NFPs.
4. f_res = c/(4·stub·√εr). Flag above min(15 mil, 0.3/Gbps), or if f_res < 3× Nyquist.

This shares its stackup model with the KiCad 10 via delay.

**I. Other checks:**
- I/O corridor;
- TVS, filter or CMC nearer the connector than the IC, with a short GND via;
- floating copper and islands;
- clock edge/period <10%;
- series R near the driver;
- running skew.

**[IF] geometric functions:**
- path order with zero vias;
- offset-polygon GND coverage;
- no T-junctions or test points;
- distance windows and annuli;
- plane-edge offset (or a shrunken keep-in area);
- loop polygon → L estimate → overshoot L·dI/dt (warn above 0.2 × Vds_max);
- trace capacitance (crystal, I2C C_b);
- AC cap near either endpoint;
- edge-finger keep-outs;
- the I2C R_P window.

**Simulation (S):**
- loss budgets;
- DDR IBIS PVT;
- termination current;
- 3-D guard analysis;
- MREMC pre-screen;
- field-solved width and gap.

**Encodability matrix:**

| Rule family | KiCad 9/10 | KiCad master | External |
|---|---|---|---|
| Width/gap per layer for Z0 | native `(layer …)` | same | S: field solve |
| Pair skew, bus skew, DDR segments | native (ps, `fromTo`) | same | — |
| Length/delay across series parts | partial | `net_chain_length` | — |
| Uncoupled length, vias, edge, angles | native | native | — |
| Return path on one layer | — | `return_path` | G: auto layer, buffers, detours |
| Reference change → via/cap | — | — | G (C) |
| Loop area | — | — | G (D) |
| Trace stubs | — | `stub_length` | G for plain nets |
| Via stubs | backdrill model only | — | G (H) |
| Crosstalk coupled length | clearance only | — | G (E) |
| Connector clustering / between | — | — | G (F) |
| Stitching / fence pitch | — | generator | G (G) |
| Protection topology; plane-edge offsets | rule areas, partly | — | G (I) |

**Open-source checkers (licence gates reuse):**

| Project | Licence | Content |
|---|---|---|
| [jasonarnoldarnie/kicad-tools `return_path`](https://github.com/jasonarnoldarnie/kicad-tools) | **None (all rights reserved) → reference only** | KiCad 10 SWIG + numpy. Reference = nearest filled layer by dielectric. Samples every 0.1 mm against a 0.05 mm raster. Flags: VOID (A* detour; FAIL >1.0 mm), ISLAND, SPLIT, TERMINAL, VIA (stitching via FAIL >2 mm; capacitor FAIL >5 mm), EDGE (w/2 + 3h). Loop-area model; HTML glow 1/(1 + (x/h)²) to ±3h; `return_path_classes.json` overrides; plane copper only |
| [aklofas/kicad-happy](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md) | MIT | Agent skill for Claude Code/Codex; 44 rules in 18 categories. Voids; transitions without a GND via; edge < h; stitching √(area/count) vs λ/20 at 3× the crystal frequency; 3H crosstalk (≥5 mm coupled); skew→common mode; ESD; connector filtering and ground-pin ratio; cavity; harmonics; PDN. 0–100 risk score (≤3 findings per rule); band prioritisation; interface risk; near-field probe points |
| [hap231/kicad-emi-guardian](https://github.com/hap231/kicad-emi-guardian) | MIT | KiCad ≥10.0.5 IPC plugin. Gaps and detours; return vias within 2 mm; coupling (≤5°, ≥5 mm overlap, ≤0.5 mm gap, grid hash); edge 1 mm; skew 1 mm; acute corners <75°; dangling stubs ≥0.8 mm; long nets (1/6); GND-pour appendage antennas ≤1500 MHz; stitching planner; dry-run, no markers |
| [tombueng/emcvisual](https://github.com/tombueng/emcvisual) | 0BSD-style | Browser TypeScript; reads KiCad 6–10, IPC-2581, ODB++ and Eagle. Biot–Savart near-field with images. About 30 rules, each with threshold, origin and test board (return-gap, ref-change, no-stitching at 3 mm, edge, cable-cm, io-coupling, long-line with no ≥10 Ω within 15 mm, filters, ESD, crystal, hot loop). Ranks by far-field share; full-wave comparison claimed but not reviewed |
| [RolandWa/KiCAD_Custom_DRC](https://github.com/RolandWa/KiCAD_Custom_DRC) | **Non-commercial proprietary → reference only** | TOML rules: GND via ≤2 mm; decap ≤3 mm; plane sampling every 0.5 mm in a 1 mm zone; edges; 3W; connector filter topology; IEC 60664-1 creepage |
| [easyw/RF-tools-KiCAD](https://github.com/easyw/RF-tools-KiCAD) | GPL-3.0 | Via fences (pyclipper), stitching, teardrops |
| rjwalters/kicad-tools | unchecked | Protocol-aware pair rules emitting native constraints [S] |

KiCad itself is GPL-3.0+; kipy is MIT.

**Commercial references:**
- **HyperLynx DRC EMI rules**, all parameterised: edge rate, edge shield, exposed length, filter placement, ICs over a split, I/O coupling, metal island, gap crossing, plane edge, reference change, via stub.
- **Other tools:** NEC EMISTREAM; IBM EMSAT (Archambeault; "hundreds of man-years" [S]); Zuken CR-8000 EMC Adviser.
- **How they classify nets:** manual entry, name substrings, a component database, or IBIS. Names alone are insufficient ([LearnEMC](https://learnemc.com/commercial-emc-rule-checkers)).
- **Clemson:** source/path/antenna combinations are computer-identifiable from layout and component data [S].

### Implications for our system

- **Checker priority:**
  1. B (return path)
  2. C (reference change)
  3. H (via stubs)
  4. F (connector between-ness)
  5. E (crosstalk, including I/O)
  6. G (stitching)
  7. I (protection, islands, edge rate)
  8. D (loop ranking)
- **Reuse:** reimplement from these specifications. Reuse code only from MIT, 0BSD or GPL-compatible projects.
- **Prefer native constraints:** KiCad 10 ps profiles and `fromTo`, and `return_path`/`stub_length` on master.

---

## 9. Rule-pack format and knowledge-base schema

**Five parts per rule** ([IF] §11):
1. A match pattern binding the rule to schematic objects.
2. Typed parameters (mm, mil, ps, Ω, nF, pF, dB, %, UI, W, H, or formulas).
3. Provenance and precedence: datasheet > vendor family > interface default > generic. **Record conflicts; never resolve them silently.**
4. A backend: `kicad_dru`, `geometric`, `simulation` or `bom`.
5. A placement intent, kept separate from routing: anchor, adjacent, order_along_path, distance_window, same_side, keepout_ring, orientation, max_loop_area or priority_order.

**YAML v0**, with precedence 10 fab < 20 interface < 30 vendor family < 40 datasheet:
- `pack{id, version, precedence, vendor_profile}`
- `applies_when{parts[{role, match{lib_regex, pin_functions, value_regex, class, nets}, optional}], nets[{role, match{pin}}]}`
- `parameters{name: {value|formula, unit, tol_pct, tag P|S|D, source, rev, by_vendor{}}}`
- `conflicts[{parameter, values[{value, source}], resolution: stricter|vendor_profile|window|ask}]`
- `placement`, `routing{netclasses, diff_pairs}`, `checks[{id, backend, severity, emit}]`, `overrides`

**Resolution order:**
1. Highest precedence wins.
2. Then `by_vendor[vendor_profile]`.
3. Then the declared resolution. The default is "stricter", which raises an `info` finding citing both sources.
4. **[S] never overrides [P]** at equal precedence.
5. [D] values are warnings until calibrated.

**Worked examples in [IF]:**
- **usb2_hs:**
  - Roles: conn, phy, esd, cmc.
  - Parameters: Zdiff 90 ±15% (with `by_vendor`); skew 1.27 mm (Qualcomm 2.0, TI controllers 3.81); length warn 150 / max 250 mm (TI 304.8); ≤4 vias; gaps 0.762 and 1.27 mm; GND overhang 5× pair gap; esd_conn_max 5 mm [D].
  - Conflicts: shield termination → ask.
  - Placement: anchor the connector to the edge; order conn→esd→cmc→phy.
  - Checks:
    - DRU: `skew … within_diff_pairs`, `via_count`, `length` with `fromTo`, clearance.
    - Geometric: no T-junctions or TPs; GND coverage; ESD path order with a GND via within 1 mm.
    - BOM: no series caps.
- **buck_sync:**
  - Parameters: Cin ≤2 mm; bulk ≤20 mm; loop 2/10/20 mm²; 5 A/ns; L1–L2 ≤0.127 mm; 1 via/A; 1 mm/A; SW ≤2.54 mm; FB ≤3 mm [D].
  - Placement: same side; inductor keep-out ring.
  - Override: the datasheet reference layout at precedence 40, with target loop area measured from the evaluation board.
- **xtal_pierce:**
  - Placement: an annulus from the vendor minimum to 12 mm; caps adjacent, CL1 first; series R by the MCU.
  - Parameters and conflicts: parasitic limits; hs_keepout 3 mm [D]; metal-can vendor switch.
  - Routing: a GND ring tied once; XIN/XOUT ≥3W [D]; no TPs.
  - DRU: disallow foreign tracks and vias in `XTAL_KEEPOUT`.
- DRU forms (`within_diff_pairs`, `insideArea`, `track_angle`) must be tested on the installed KiCad.

**Knowledge-base record** ([HS] §12 + VR):
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
2. LLM confirmation from pin functions and datasheets.
3. User overrides (as in `return_path_classes.json`).

Then assign each net a t_r, and treat all pins of fast ICs as noisy.

### Implications for our system

- One interface/net-class table drives both the native KiCad constraints and the Python checker suite. Every emitted rule carries `rule_id`, `source_url` and `provenance`.
- Packs are data, not code, so they can be calibrated later against vendor evaluation-board layouts.

---

## 10. Idea inventory

Source tags: [HS] rules_highspeed_emi.md; [IF] interface_rule_packs.md; [VR] verification_rules.md.

**Physics and modelling**
1. Encode physics, not slogans; myths become negative rules carrying their replacement check [HS].
2. Return current flows directly under the trace, hence the continuous-reference rule [HS].
3. The ±1h/±3h/±10h spread justifies edge and void offsets (1.5W ≈ 3h) [HS].
4. A via through the same plane is not a discontinuity; avoid false positives [HS].
5. Merge antipads into void polygons and measure slot length perpendicular to the trace [HS].
6. Ott's four-level layer-change order as the router policy [HS].
7. Return vias ≤200 mil, scaled by data rate (~5 / 2.5 / 1.3 mm) [HS][IF].
8. Stitching caps only at split crossings (≤1 µF); never cite 1–10 nF/50 mil as primary [VR].
9. Avoid power-plane references; never overlap non-referencing planes [HS].
10. No ground traces or fill on plane boards; ground through direct vias [HS].
11. 10:1 signal-to-ground via ratio (Johnson's 3-D scaling) [HS].
12. Differential pairs return per leg; apply return rules to each leg [HS].
13. Johnson's skew-to-common-mode formula (20% skew → 10% CM) [HS].
14. Critical length: t_r/6 flags SI review, t_r/2 must terminate (contested) [HS][VR].
15. Slow edges first; default series R; transition time ≈20% of UI [HS].
16. Choose termination for minimum harmonic current [HS].
17. Stub limit min(15 mil, 0.3/Gbps), counting pad rings [HS][VR].
18. Decide the stub strategy before the stackup [HS].
19. Enter connector pads from the non-stub end; TH receptacles from the bottom [HS][VR].
20. Johnson's K formula with saturation and aggressor summation [HS].
21. Spacing from a K budget: D ≥ H·√(1/K − 1) [HS].
22. Reduce crosstalk through h first [HS].
23. Guard traces only in stripline, end-shorted and length-matched [VR].
24. Stricter crosstalk budgets for I/O and analog victims [HS].
25. Orthogonal adjacent signal layers [VR].
26. Three-condition antenna model; 1 mV / 100 µV between antenna parts [HS].
27. MREMC as the computable common-mode EMI estimator [HS].
28. Ott's DM/CM formulas; 5/15 µA cable limits [HS].
29. FCC 15.109 limits as the E_max target [HS].
30. Consistency checks linking 1 mV, 3.6 µA and Class B [HS].
31. Cavity-resonance formula for stitching [HS].
32. No spread-spectrum clock as a reference for transceivers, PLLs or RF [HS].
33. Every pin of a fast IC is a potential HF source [HS].

**Stackup**
34. Ott's four factors and five objectives; 8 layers minimum for all five [HS].
35. Candidate stackup library for 4/6/8/10 layers [HS].
36. 8-step stackup selection and scoring algorithm [HS].
37. Ott vs Hartley on 6 layers as a warning with rationale [HS].
38. Penalty for forced P↔G reference changes [HS].
39. Plane pair <0.25 mm when ≥3 power pins share a rail [HS].
40. Power planes on one layer; gap ≥ plane-to-ground spacing (≥3 mm "maybe") [HS][VR].
41. Stackup before placement [HS].
42. Microstrip vs stripline as a context switch [VR].
43. Fibre weave: 10–35° rotation or zig-zag [VR].
44. Ott's impedance and delay rules of thumb as a fallback [HS].
45. Fab stack and material data as inputs [IF][VR].

**Differential pairs**
46. skew_max = min(spec, 0.1·t_r) via per-layer delay [HS].
47. Running-skew compensation near the mismatch [HS].
48. Place ICs so pairs exit and enter in the same direction [HS].
49. Switchbacks ≪ ⅓ t_r or uncoupled; jogs ≥3W; spread <2S [HS][VR].
50. Coupling tighter than 0.5 mm buys no EMI [HS].
51. GND vias pinning the planes at differential vias (XFP) [HS].
52. Absolute keep-outs: 30 mil to signals, 50 mil to clocks [VR].
53. Uncoupled length ≤45 mil; breakout ≤0.25 in [VR].
54. Equal via counts; family-scoped via limits [VR].
55. 30 mil antipads; no non-functional pads [VR].
56. Symmetric 0402 in-line parts; 100%, 2-layer pad voids [VR][IF].
57. Bends >135°, balanced left/right [VR][IF].
58. KiCad pair-to-pair clearance condition [HS].

**Interface packs**
59. Mandatory vendor profiles; tightest [P] value when the vendor is unknown, plus info [IF].
60. Chain order connector→ESD→CMC→AC cap→PHY [IF].
61. Qualcomm's 5 ps as the "physics-justified relaxed" USB3 option [IF].
62. Per-via length penalty (~25–50 mm) in the SerDes cost [IF].
63. ESD+CMC ≈1 in length cost [IF].
64. USB shield conflict resolved by asking [IF].
65. Type-C CC: width, capacitance window, no series passives [IF].
66. PCIe L_max from loss budgets and material tables [IF].
67. AC cap at either endpoint; never mid-line [IF].
68. 176–220 nF as the universal Gen3+ BOM window [IF].
69. Edge-finger inner-layer keep-outs [IF].
70. Lane-to-lane matching only on device demand [IF].
71. DDR: one `fromTo` rule per SDRAM per group [IF].
72. Never emit cross-byte DDR skew [IF].
73. 20% derating as opt, the limit as max, then IBIS simulation [IF].
74. Micron 1%-of-period default [IF].
75. Stackup delay model instead of a fixed ps/mm constant [IF].
76. Ethernet PHY↔magnetics soft window (~25 mm; >76 mm error) [IF].
77. Ethernet ESD location as a pack parameter [IF].
78. Chassis island and Bob Smith rules as clearances [IF].
79. UI-based skew formulas resolved at the data rate [IF].
80. D-PHY length table with a `cable_il_db` input [IF].
81. SATA polarity is controller-dependent [IF].
82. CAN/RS-485: termination only at end nodes; protection in the signal path [IF].
83. I2C pull-up window from stackup capacitance [IF].
84. SD CLK↔data matching; series R at the source [IF].
85. Slow multi-drop clock star and daisy limits [IF].
86. Crystal annulus placement [IF].
87. Crystal parasitic score from trace length × C′ [IF].
88. Crystal metal-can and under-copper conflicts as vendor switches [IF].
89. C-shaped GND via ring at clock and RF transitions [IF].
90. Buck pack: Cin <2 mm, loop tiers, L → overshoot [IF].
91. Inductance anchors make "minimise the loop" scoreable [IF].
92. Datasheet reference-layout override at precedence 40 [IF].
93. Fab packs set min only; interface packs never relax them [IF].
94. Derived mounting-hole keep-out (RP2040, 6 mm) [IF].

**EMC placement**
95. Cluster cabled connectors on one edge or corner [HS].
96. No HS between connectors, scored with MREMC [HS].
97. 2 cm I/O-zone defaults [HS][VR].
98. Clear I/O corridor; no HF under I/O parts [HS].
99. I/O nets end in series or filter parts at the connector [HS].
100. TVS topology as comparative constraints [VR].
101. TVS GND via adjacent to the pin; ESD-path corners ≤45° (2.6 mm arc) [VR].
102. Via only after the TVS (Case 1) [VR].
103. CMC within ~5 mm as a soft target [VR].
104. Edge rules: 90 mil from plane edge, 2X from board edge, 3W [VR].
105. Plane-edge offset as a zone-boundary check [VR][IF].
106. Largest-unstitched-region metric reconciles the stitching debate [HS].
107. Split-boundary stitching every 10–15 mm (soft) [VR].
108. Chassis bond via an overlapping layer, SMT caps and one LF tie [HS].
109. One partitioned ground; ≥14-bit isolated regions joined under the ADC [HS].
110. 300 mV check only when a split is deliberate [VR].
111. Optional filter, TVS and shield footprints [HS].
112. Two EMC reviews: before layout and at the first draft [HS].
113. Visualise each compliance test's current path [HS].
114. Clamp-measure every cable [HS].
115. Ott's red flags as lint; invert the maximize-emission list [HS].
116. emcvisual placement thresholds [HS].
117. 7-step placement order (1–3 hard, 4–6 soft) [HS].
118. Placer costs: V_cm, I/O intrusion, length, crossings, direction alignment [HS].

**Classification and verification**
119. Hard / soft-strong / soft-weak / context-switch tiers [VR].
120. Blog mm values become rank objectives [VR].
121. `source_scope`, `statement_strength`, `contested_by` fields [VR].
122. LLM converts relative language into comparative constraints [VR].
123. Severity recalibrations (TL-5, EMI-7, EMI-6, RF-05) [VR].
124. Corner rule scoped to ESD and RF classes [VR].
125. Contested rules are never defaults [VR].
126. Montrose's conditions as the 20-H selector [VR].
127. Store part-specific numbers per part [VR].

**Encoding and checkers**
128. KiCad 10 ps constraints and `fromTo` [HS][IF].
129. Emit master `return_path` and `stub_length` when available [HS].
130. Checker A: reference map [HS].
131. Checker B: return continuity (A* detour) [HS].
132. Checker C: reference-change via or cap [HS].
133. Checker D: loop ranking [HS].
134. Checker E: crosstalk by spatial hash [HS].
135. Checker F: connector clustering and between-ness [HS].
136. Checker G: largest empty circle vs cavity and λ/20 [HS].
137. Checker H: via stubs and f_res [HS].
138. Checker I: protection, islands, edge rate, I/O corridor [HS].
139. [IF] geometric functions (order, coverage, windows, loop L, trace C) [IF].
140. HTML/JSON overlay for findings (no IPC DRC markers) [HS].
141. Parse the stackup from `.kicad_pcb` or IPC `get_stackup` [HS].
142. Use the master GUARD generator for via fences [HS].
143. Licence gating for code reuse [HS].
144. Rank findings by consequence [HS].
145. Expert-system framing over full simulation [HS].

**Format and knowledge base**
146. Five-part rule definition [IF].
147. YAML pack schema with `by_vendor`, `conflicts` and `resolution` [IF].
148. Resolution policy: [S] never overrides [P]; [D] defaults to warning [IF].
149. Knowledge-base schema with `basis` (h, λ, fraction of t_r) [HS].
150. Net classification: regex → LLM → user overrides [HS].
151. Per-net t_r, flagged when estimated [HS].
152. Calibrate [D] values against vendor evaluation boards [IF].
153. Test emitted DRU syntax on the installed KiCad [IF].
154. Closing the loop (constraints → route → physics check) is an unoccupied niche [HS].
