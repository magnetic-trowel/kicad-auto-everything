# Thermal design: metrics, copper area, thermal vias, placement, screening estimator

**TL;DR**
- **R_θJA is a property of the JEDEC test board.** 70–95% of the heat leaves through the board, and PCB design is its strongest influence. Never size copper from R_θJA alone; build a resistance network.
- **TI rules of thumb (SNVA419):**
  - ≥15.3 cm²/W of two-sided solid copper for a 40 °C rise in still air;
  - ~261 °C/W per 12 mil via, so use as many as fit at 1 mm pitch;
  - 1 oz base, 2 oz above 3 W, 4 oz above 6 W;
  - no copper cuts perpendicular to heat flow;
  - bottom-side heatsinking.
- **Exposed-pad (EP) vias:** 0.3 mm at 1.0–1.2 mm pitch, direct-connect (no spokes). Tenting is **CONTESTED** between TI documents.
- **Placement:** spread hot parts, keep them out of corners, and keep electrolytics, crystals, references and CJ sensors upstream of and away from them.
- **A first-order screening estimator is cheap enough to run on every candidate placement.**

## Key facts

**Metrics** (TI SPRA953D, [PDF](https://www.ti.com/lit/pdf/spra953)) [P]:
- R_θJA is "most commonly reported and most often misused". In still air "almost 70%–95% of the power … is dissipated from the test board".
- Influence on R_θJA: PCB design 100%; chip/pad size 50%; package geometry 35%; altitude 18%; ambient 7%; power 3%.
- 1s vs 2s2p test boards shift R_θJA by up to 50%. Use R_θJA(effective) for the real system.
- Ψ_JT is 0.5–2 °C/W vs R_θJC 4–15 °C/W; T_J = T_top + Ψ_JT·P.
- Ψ_JB back-calculates T_J from a board thermocouple. Do not use Ψ_JT with a heatsink.

**TI SNVA419C** (AN-2020 "Thermal Design By Insight, Not Hindsight", [PDF](https://www.ti.com/lit/pdf/snva419)) [P]:
- **Rule 1:** ≥15.29 cm² (2.37 in²) of two-sided solid copper per W for a 40 °C rise, natural convection, no heatsink. Airflow can reduce this "by up to half". Alternative: area ≥ 500 °C·cm²/W ÷ (θ_JA − θ_JC). This assumes no enclosure blockage and an EP tied to planes that reach the board edge. Inner planes improve a good 2-layer design by up to 30%.
- **Rule 2:** a 12 mil via with 0.5 oz walls ≈ **261 °C/W**. "As many thermal vias as will fit underneath the exposed pad … with 1mm spacing", on as many layers as possible, with a solid bottom ground.
- **Rule 3:** ≥1 oz; 2 oz above 3 W; 4 oz above 6 W. Example: 3 × 3 in 2-layer θ_JA 28.3 → 21.2 °C/W going from 1 to 2 oz (25% better).
- **Rule 4:** a cut perpendicular to heat flow added 5.5 °C, vs 1.5 °C for a parallel cut. Route traces through spreaders radially.
- **Rule 5:** plastic package tops have θ_JT 50–200 °C/W, so heatsink the board bottom through the EP and vias.
- **Rule 6:** superposition "almost works" (slightly non-linear).
- **Constants:** λ_Cu ≈ 4 W/cm·K; FR-4 ≈ 0.0023 W/cm·K; h ≈ 10 W/m²K. 1 cm² of 1 oz copper laterally ≈ 71 °C/W; FR-4 vertical for 1 cm² ≈ 13.9 °C/W.

**TI SLMA002H** (PowerPAD, [PDF](https://www.ti.com/lit/pdf/slma002)) [P]:
- Thermal land directly under the package; TQFP maximum land = body − 2.0 mm, solder-mask-defined.
- Diminishing returns from vias; 5–9 are adequate for a small die.
- Example 0.33 mm (13 mil) vias with 1 oz plating: barrel copper ≈ 1% of land area.
- Don't leave the PowerPAD unsoldered.

**TI SLVA959B** [P]: continuous pours from the pad; direct-connect, unmasked thermal vias (thermal relief "reduce[s] the flow of heat"); doubling copper thickness halves lateral R. Its 5.73 °C/W per-via figure is **wrong** ([power/motor-drivers.md](power/motor-drivers.md)).

**EP via geometry and assembly** (VR):

| Source | Geometry | Mask/fill |
|---|---|---|
| [TI SLOA122](https://www.ti.com/lit/pdf/sloa122) [P] | ≤0.3 mm, 1 mm pitch | "Do not cover the vias with solder mask which causes excessive voiding"; no spokes; plugging "not necessary or recommended" |
| [TI SLUA271C](https://www.ti.com/lit/pdf/slua271) [P] | ~1.0 mm pitch, 0.3 mm start | Plug or tent; top tent with mask 0.1 mm larger than the hole "less likely to produce random voids" |
| [Renesas TB389](https://www.renesas.com/en/document/oth/tb389-pcb-land-pattern-design-and-surface-mount-guidelines-qfn-packages) [P] | 1.0–1.2 mm pitch, 0.3–0.33 mm, ~1 oz barrel, to buried planes | "Tenting from the top is considered a better option"; tent ~100 µm larger |
| Rohm [P] | 0.3 mm, ~1.2 mm pitch | Small vias fill with solder; beware suction through open vias |
| MPS AN065 [P] | 10 mil drill / 20 mil pad near IN/GND | — |
| TPS62130 DS [P] | — | Vias under paste "filled, plugged or tented" |
| NXP AN1902 | Tent ≥ via + 0.10 mm | 404, NOT RETRIEVABLE (same value confirmed by TI and Renesas) |

**Paste and voids.**
- EP paste 50–70% (TI SLUA271), 50–80% (Renesas, Maxim) in multiple smaller apertures. A 1:1 aperture can "float" the part.
- Voids: IPC-A-610 via pSemi says ≤25%. TI calls 25% the point of diminishing returns but "prefers a limit of 50%" in high-power applications (VR +CTX).

**Secondary numbers** [S]: ~150 °C/W per 0.3 mm via (25 µm plating, 1.6 mm board; R = L/(kA), k = 385); a 9-via array ≈ 17–33 °C/W; filled vias (IPC-4761 VII) claimed 6–8× better ([rftools](https://rftools.io/calculators/pcb/via-thermal-resistance/)). Stack-ups are anisotropic; build 3-D paths with planes and vias ([Salitronic](https://salitronic.com/kb/thermal-management/)).

**Placement** (vendor guidance, low–medium authority) [V]:
- Don't put a tall part upstream of a hot one (a 10 mm electrolytic created a stagnant wake). Put sensitive parts on the cool upstream side; align tall parts with airflow.
- Separate high-power parts (two 2 W parts 5 mm apart share one copper patch and their rises add; 5–10 mm as a start). Keep them out of corners ([NextPCB](https://www.nextpcb.com/blog/pcb-thermal-design-basics-2-component-layout); [ALLPCB](https://www.allpcb.com/blog/pcb-assembly/thermal-aware-component-placement-a-guide-to-preventing-overheating-on-pcbs.html)).
- Electrolytic life roughly doubles per 10 °C cooler (Arrhenius simplification, ignoring voltage and ripple; polymer caps differ). A worked example assumed +35 °C near IGBTs ([CapXon](https://www.capxongroup.com/files/Lifetime%20Compendium_EN.pdf)).
- 2 in² of copper lowered component temperature 10–15 °C (illustrative, JLCPCB).

**Screening estimator** (RPA §18) [I]:
1. **Power per part:** LDO (V_IN − V_OUT)·I; switcher P_out·(1/η − 1), split IC/L/diode; resistors I²R; LEDs (1 − η)·P.
2. **Spreading area:** flood-fill the zone graph from the EP/pad through the vias, clipped where lateral R exceeds a cutoff.
3. **Network:** R_J→pad (θ_JC or Ψ_JB) + R_via-array (261 °C/W ÷ N, scaled for drill and plating) + lateral L/(λ·W·t) + 1/(h·A_eff, both sides).
4. **Superpose** sources by influence coefficients.
5. **Check** T_J < T_J,max − margin. Sensitive parts (Al-electrolytics, crystals, references, CJ sensors) stay within limits with small ΔT to their neighbours.

**Rules** (RPA §5, §18) [I]:

| ID | Rule | Numeric | Check | Sev |
|---|---|---|---|---|
| TH-01 | EP via array to GND/thermal planes on ≥2 layers | 0.3 mm, 1.0–1.2 mm; count ≈ EP area / pitch²; P ≳0.3 W | Via count/pitch; connected zone area | S2 |
| TH-02 | Fill or tent strategy compatible with assembly | Tent ≥ via + 0.1 mm or plugged (IPC-4761) | Via attribute / mask expansion | S3 (CONTESTED) |
| TH-03 | Windowpane paste on EPs > ~2 × 2 mm | 50–70% | Paste area / pad area | S3 |
| TH-04 | Copper area per dissipating part from P and θ | Start from the datasheet θ test board | Estimated P vs connected copper | S2 |
| TH-05 | Spread heat sources; avoid corners | ≥5–10 mm between >1 W parts [V] | Pairwise distance | S3 |
| TH-06 | Temperature-sensitive parts away from and upstream of hot parts | ≥10 mm or outside the hot-spot radius [I] | Sensitive-to-hot distance; airflow vector | S2 |
| TH-07 | Tall parts parallel to airflow, not upstream of hot parts | — | Upstream-cone test | S3 |
| TH-08 | No SW-node copper as heatsink; use PGND/EP + vias | — | SW area cap | S2 |
| TH-09 | Never size from R_θJA alone | — | Estimator | S2 |
| TH-10 | Minimum copper per watt | ≥15.3 cm²/W | Connected area vs P | S2 |
| TH-11 | EP vias 1 mm pitch, as many as fit, every plane, direct-connect | 0.30–0.33 mm | Pitch/count; zone connection solid | S2 |
| TH-12 | Copper weight by dissipation | 1 / 2 / 4 oz at 3 / 6 W | Stack-up vs total P | S3 |
| TH-13 | No breaks perpendicular to heat flow near hot parts | 5.5 vs 1.5 °C | Slot/track angle vs radial within r | S3 |
| TH-14 | Heatsink on the board bottom under the EP | θ_JT 50–200 °C/W | Heatsink side vs EP | S3 |

## Recommendations for our system
- **Run the estimator inside the placement loop.** The LLM extracts I, η, θ_JC and Ψ_JB from datasheets; code computes.
- **Thermal aggressor and victim classes** feed the [criticality map](checkers-power.md) and distance penalties.
- **Make tenting an assembly-process context switch,** not a default.

## Conflicts and open questions
- **Tenting:** SLOA122 vs SLUA271/TB389.
- **Void limit:** 25% vs 50%.
- **The estimator is first-order.** SNVA419 says it doesn't replace FEA. No JESD51-7 board definitions or package copper-area curves were extracted.
- **Distances are heuristics.** No primary minimum electrolytic-to-heat-source distance was found.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 5, § 11, § 18](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also: [power/high-current.md](power/high-current.md), [power/ldo.md](power/ldo.md), [checkers-power.md](checkers-power.md), [dfm-fab-limits.md](dfm-fab-limits.md)
