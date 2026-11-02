# EMC placement: radiation mechanisms, connector zoning, TVS/CMC, stitching, edges

Scope: radiation mechanisms and limits, connector zoning, I/O filtering and protection topology, edges, stitching, grounding/chassis, pre-compliance practice, placement priority. Not here: return paths -> [si-fundamentals.md](si-fundamentals.md); checkers -> [checkers-si-emi.md](checkers-si-emi.md); contested rules -> [myths-and-contested.md](myths-and-contested.md).
Keys: EMC, EMI, common mode, V_cm, I_CM, cable radiation, MREMC, emcvisual, kicad-happy, Ott, Hubing, LearnEMC, FCC 15.109, Class B, connector zoning, I/O zone, TVS, ESD, SLVA680A, CMC, edge clearance, stitching, perimeter vias, chassis bond, one ground, LSB, red flags, placement priority
Tags: [P] primary, [S] snippet, [I] inference; VR statuses as in [si-fundamentals.md](si-fundamentals.md).

## EMC placement rules
1. Radiators are cables and chassis (the only efficient antennas below ~100 MHz). ~1 mV between two cable reference points can fail Class B (100 µV under stricter limits): never let a voltage develop between connectors.
2. Placer costs: MREMC "between connectors" V_cm estimate ([checkers-si-emi.md](checkers-si-emi.md) checker F); I/O-zone intrusion; fast-net length and crossings; pair direction alignment; crystal, inductor, switch-node distance to edges and connectors (emcvisual thresholds).
3. TVS and CMC as comparative topology constraints: d(TVS, connector) < d(TVS, IC), zero vias before the TVS, GND via at the TVS pad. Never mm DRC errors (TI gives no mm; "TVS within 5–10 mm", "CMC within 5 mm" are soft).
4. Edges per layer: `edge_clearance` ≥2h for fast classes; geometric check ≥90 mil from plane edges on HS diff pairs (TI scope), else w/2 + 3h; `edge_clearance` covers only Edge.Cuts, so plane edges need a zone-aware check; keep-out rule areas for the I/O zone.
5. Stitching: one "largest unstitched region" metric (sidesteps perimeter-vs-distributed); KiCad master's GUARD generator for fences.
6. Always add optional footprints (CMF 0 Ω, TVS, shield-can pads, chassis R/C) when compliance is uncertain.
7. Rank findings by estimated V_cm or I_CM, not by violation count.

## Radiation mechanisms and thresholds
**Antenna model** ([LearnEMC](https://learnemc.com/pcb-layout) [P; VERIFIED]): needs two parts not electrically small with a voltage between them. <~100 MHz only cables and chassis; >100 MHz also tall parts, heatsinks, seams, sparsely populated planes. ICs, traces, dense planes are poor antennas. Hold antenna parts within 1 mV (100 µV for limits stricter than CISPR 32 B).

**Magnetic coupling between connectors:** return flux wraps the plane: "tens of mA at tens of MHz" induces mV, more with wider/higher traces; stripline induces nothing. Fix: connectors on one edge, or bond chassis to plane at both connectors.

**MREMC common-mode algorithm** ([CMode_algr.js](https://learnemc.com/ext/calculators/mremc/calculator/CMode_algr.js) [P], Hubing/Su/Zhu; Su & Hubing 2011 IEEE T-EMC 53; Zhu & Hubing CVEL-13-051):
- `L_ret = (µ0/π)·t·l_t/w_e/√(1 − 4(1 − 2t/w_e)·offset²/w_e²)`, w_e = d1 + d2 (distances to the two board edges), offset = |d1 − d2|/2.
- `L_trace = √(µ0ε0)·l_t·Z0`; imbalance `h = L_ret/(L_ret + L_trace)`.
- V_cm: voltage-driven `h·V_dm`; current-driven `2πf·L_ret·I_dm`, I_dm = V/R_L or V·2πf·C_L.
- `E_max = F_max·0.55·V_cm·boardfactor·cablefactor`; boardfactor = sin(2πL_eff/λ) if λ ≥ 4L_eff else 1; cablefactor = sin(2π·1 m/λ) if λ ≥ 4 m else 1; F_max = 2/sin(√(c/(f·L_cable))) above cable half-wave resonance. L_eff depends on which side of the trace each cable connector sits.
- Assumes no shielded enclosure, cable ≫ board, ~1 m above ground.

**emcvisual** ([RULES.md](https://github.com/tombueng/emcvisual/blob/main/docs/RULES.md) [P]): cable CM `L_p = (4/π²)µ0·l·h/(d1 + d2)`, V = ωL_p·I, E = 0.365·V (Hockanson/Hubing 1996). I/O coupling `M = µ0/(4π)·ln(1 + 4h²/s²)`, E = 40·V/Z_ant, Z_ant = 80(N+1) Ω.

**Ott's formulas** (via kicad-happy, secondary to Ott's book; [MIT](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md) [P]): DM loop `E = 2.632×10⁻¹⁴·f²·A·I/r`; CM cable `E = 1.257×10⁻⁶·f·L·I_CM/r`. 2× loop area +6 dB; 2× frequency +12 dB.

**Cable CM current limits:** Ott <5 µA Class B, <15 µA Class A, cables ≥1 m (10 µA at 0.5 m); measure with clamp probe (F-33-1, 2–250 MHz), iterate over every cable (fixing one can raise another) ([Ott](https://hott.shielddigitaldesign.com/techtips/tips-cm.html) [P]). Hartley: 8–10 µA fails Class B.

**FCC §15.109** ([CFR](https://www.law.cornell.edu/cfr/text/47/15.109) [P]):

| Class | Distance | 30–88 MHz | 88–216 MHz | 216–960 MHz | >960 MHz |
|---|---|---|---|---|---|
| B | 3 m | 100 µV/m | 150 µV/m | 200 µV/m | 500 µV/m |
| A | 10 m | 90 µV/m | 150 µV/m | 210 µV/m | 300 µV/m |

**Consistency checks** [I]: Ott CM formula, 1 m cable, 3 m, 150 µV/m at 100 MHz → ~3.6 µA (consistent with 5 µA). 1 mV and 5 µA are one rule at typical CM impedance; MREMC numbers -> [fields-emi-budget](../physics/fields-emi-budget.md#4-consistency-checks).

**Other mechanisms:** cavity resonance `f_mn = (c/2√εr)·√((m/L)² + (n/W)²)`, independent of plane spacing ([LearnEMC calc](https://learnemc.com/ext/calculators/cavity_resonance/pcb-res.html) [P]). Every pin of a fast-clocked IC is an HF source; near-field scans show DRAM supply pins carry more current than its signal pins (LearnEMC).

## Connector zoning
Source: [LearnEMC good guidelines](https://learnemc.com/other-good-emc-design-guidelines) [P; VERIFIED, numeric defaults added by VR]; LearnEMC labels them "situational".
- Cabled connectors on **one edge or one corner**.
- **No HS circuitry between connectors** (guideline #3: "one of the most common problems"); if unavoidable, metal chassis bonded at both connectors.
- Each I/O device **within ~2 cm** of its connector; each device's off-board links through one connector.
- Non-I/O parts **≥2 cm** from I/O nets and connectors ("not necessarily the best advice in every situation").
- No unrelated trace between a connector and its device; no HF signal under I/O components.
- Clock drivers next to their oscillators; parts that talk only to each other together. Minimise vias on HF nets; tie unused digital inputs high or low.
- **Worst guideline:** "group by type, HS farthest from the connector" ([LearnEMC worst](https://learnemc.com/some-of-the-worst-emc-design-guidelines)); put parts that talk through a connector next to it.

## I/O nets, filters, protection
Source: [LearnEMC PCB Layout](https://learnemc.com/pcb-layout) [P].
- Each I/O net ends in a series or filter component near the connector; an IC driving a cable directly must not inject >~1 mV CM.
- Filters with minimal parasitics; avoid higher-order filters that ring.
- A CMC must filter a **balanced** pair. **Never put a ferrite on ground.**
- IC protection to that IC's ground; board protection to the EMC ground; connection inductance is critical.
- Metal enclosure: send ESD current to the enclosure without pulling it onto the board. Plastic: check arc paths through seams; slow high-impedance inputs with resistors.

## TVS topology
Source: [TI SLVA680A](https://www.ti.com/lit/pdf/slva680) [P]; VR: topology VERIFIED, mm distance NOT FOUND.
- TVS "as near to the connector as design rules allow"; protected IC "much further from the TVS than the TVS is to the connector".
- No stubs, no via between ESD source and TVS. If a via is unavoidable: source → TVS first, then via (Case 1); avoid Case 2 (IC branch before the via).
- 8 kV strike → dI/dt = 4×10¹⁰ A/s, so **0.25 nH extra adds 10 V** at the IC.
- Corners on the strike path: 90° develops ≥7 kV and arcs at radii below **~2.6 mm**; use curves, 45° maximum; keep-out for unprotected traces.
- TVS ground: one via **immediately adjacent** to the GND pin into a same-layer plane coupling to an adjacent plane; TI example 4 stitching vias + chassis screw; BGA-TVS via 0.254 mm pad, 0.152 mm drill, epoxy-filled and plated over, 0.1 mm clearance; GND vias as large as possible.
- 5–10 mm TVS distance comes from blogs (soft). emcvisual flags a diode nearer the IC than the connector, or with no ground pour/via within 2 mm.
- Exception: Ethernet ESD on the PHY side of magnetics (TI SNLA387) -> [interfaces/ethernet.md](interfaces/ethernet.md).

## CMCs and filters
- TPS case study: CMC >30 mm from DC input failed CISPR 25 Class 5; **within 5 mm** passed ([TPS](https://tps-elektronik.com/en/case-studies/how-to-pass-automotive-conducted-emissions-cispr-25-class-5-with-tps-split-ground-plane-and-common-mode-choke-placement-emc-layout-guidelines-for-automotive-dc-dc-converters/) [P; VERIFIED case study, medium authority]).
- TI: AC caps on the protected side of the CMF; 0402 0 Ω no-stuff footprint as CMF alternative.
- emcvisual flags a ferrite, inductor or shunt cap on a cable line >10 mm from the connector pin.
- CAN: protection in the signal path ([interfaces/can-rs485.md](interfaces/can-rs485.md)).

## Edges
VR closed this gap with three primary numbers.

| Rule | Value | Source |
|---|---|---|
| Distance from reference-plane edge | ≥90 mil (2.29 mm) for HS differential pairs | [TI SPRAAR7J p.9](https://www.ti.com/lit/pdf/spraar7) [P] |
| Distance from board edge | ≥2X, X = distance from trace to its return | [LearnEMC](https://learnemc.com/other-good-emc-design-guidelines) [P] |
| Distance from GND-plane edge | >3W | [u-blox NORA-B2](https://content.u-blox.com/sites/default/files/documents/NORA-B2-u-connectXpress_SIM_UBXDOC-465451970-3906.pdf) [P] |
| Others | TI Gen5: ≥5·max(W,H). Microchip: SS ≥5W from plane edges and splits, narrow floods via'd at corners and ends. Pulse: more than trace height; Ethernet PHY ≥25 mm from edge. Ours: centreline ≥ w/2 + 3h | IF §9 [P]; HS [I] |
| Thresholds in existing checkers | kicad-happy < h (outer layers); EMI Guardian 1 mm; emcvisual <3h (≥1 mm) over ≥3 mm | [P] code |
| Edge guard band | Plane-copper guard band along the edge: most effective suppression of edge-driven CM | [ResearchGate](https://www.researchgate.net/publication/3056626_Common-Mode_Current_Due_to_a_Trace_Near_a_PCB_Edge_and_Its_Suppression_by_a_Guard_Band) [S] |

## Stitching
CONTESTED.
- Perimeter vs distributed: Ott stitches the two grounds of a G/S/S/G board around the periphery (Faraday cage). LearnEMC rates "perimeter vias every 2 cm" not-so-good: usually unnecessary; a perimeter-only ring "will create a resonant cavity"; distribute instead ([LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines)).
- No primary source gives λ/20 or a 3–5 mm stitching pitch; λ/20 is Ott's *aperture* red flag (6" at 100 MHz).
- Split boundaries: TPS case study stitch every **10–15 mm**; failed at 40–50 mm, passed at 12 mm; "Above 100 MHz the slot … acts as an effective antenna" [VERIFIED, medium authority, soft].
- Johnson: via row at ~¼" pitch; 10:1 signal:ground via ratio for 0.063" vias at ~500 ps edges (SerDes pairs follow vendor return-via rules, [diff-pairs.md](diff-pairs.md)). u-blox: stitched GND ring at board edge, power planes kept back. KiCad master `PCB_VIA_STITCH`: default pitch max(2 mm, 2× via diameter).

## Grounding and chassis
- **One ground.** Hubing 2019: "more than one ground" is MOST EGREGIOUS; "1 solid ground plane under all digital logic" ([slides](https://r6.ieee.org/scv-emcs/wp-content/uploads/sites/111/022019ToddHubing.pdf) [P]). Clearing ground under magnetics, inverters or HV is fine; gapping is not. Required galvanic isolation barriers are outside this rule ([isolation-creepage.md](isolation-creepage.md)).
- **Chassis bonding:** chassis layer *overlapping* digital ground, bonded with multiple SMT caps + one LF connection: low impedance >30 MHz, isolation <~100 kHz. Never a single-point bond at the I/O by default, never at the oscillator. "Bond (at RF) everything that leaves the board." Near metal structure: "Connect to it!"
- **Mixed signal (Ott)** ([P](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html)): one plane, partitioned, routing discipline on all layers. LSB table and resolution-based strategy -> [analog-mixed-signal.md](analog-mixed-signal.md#ott-on-split-grounds-and-lsb-budget) (12-bit 240 µV, 16-bit 15 µV at 1 V). At ≥14 bits: isolated regions solidly joined under each ADC, no trace on any layer crossing the slots. Experiment: split with 0 Ω jumpers every ½", compare.
- **Power stages (LearnEMC):** minimal switch-node area away from conductors; mind switching-loop magnetic coupling; switch modern DC-DC in the MHz range, no isolated power grounds; transitions >~1% of period cost efficiency ([power/buck.md](power/buck.md)).
- **Deliberate splits only:** MT-031: >300 mV between planes risks latch-up. DA9080 PMIC mandates GND cuts between bucks → datasheet override [VR].

## Pre-compliance practice
- **LearnEMC 10-step review**, before layout and at first draft: (1) ground structure and I/O; (2) plane extent, no gaps; (3) ground traces and fills (remove); (4) power on a plane pair <0.25 mm apart; (5) I/O nets; (6) filters; (7) transition times; (8) critical parts (op-amp loops over the plane, PLL ferrites, no ferrite on ground); (9) power inverters; (10) each test's current path (CE, RE, BCI, RI, EFT, ESD). Include footprints for optional filters, TVS, shields.
- "Blindly adhering" to EMC rule lists fails: identify sources, victims, coupling paths ([LearnEMC](https://learnemc.com/effective-application-of-emc-design-guidelines)).
- **Johnson** ([emisim](https://www.sigcon.com/Pubs/edn/emisim.htm)): simulators cannot handle real EMI; useful tools are "more like expert systems"; "2× last year's design needs another 6 dB"; run an EMI preview scan early.
- **Hubing's seven common errors:** blindly following guidelines; uncontrolled transition times; not following currents; not identifying critical traces; more than one ground; improper decoupling; bypassing filters.
- **Ott's red flags** ([P](https://hott.shielddigitaldesign.com/techtips/red_flags.html)): clock edges <10% of period; apertures >λ/20; split grounds; traces crossing slots; pigtail shields; backshells not contacting the enclosure; paint in seams; signal layers not adjacent to a plane; parallel decaps of multiple values; ungrounded fill or thieving; unshielded unfiltered cables; single-point circuit-to-chassis bond.
- **Ott's satirical "maximize emission" list**, inverted, worth 20–30 dB ([P](https://hott.shielddigitaldesign.com/techtips/maxemission.html)): avoid fast edges below 1 ns; clocks off the board edge and out of the I/O area; no slots; no clock traces across isolated grounds; more than one decap per IC; I/O filters at cable entry; no pigtails; bond logic ground to chassis at the I/O; no painted seams; AC filter at cord entry. For buried planes, ask the fab for one etched-but-unlaminated set.
- **kicad-happy pre-compliance outputs** [P]: band prioritisation by emission-source count; interface risk ranking; XY near-field probe points; 0–100 risk score capped at 3 findings per rule.

## emcvisual placement thresholds
[P]
| Part or feature | Threshold |
|---|---|
| Crystal | ≥5 mm from edge, ≥10 mm from cable connectors |
| Storage inductor | ≥3 mm from edge, ≥10 mm from cable connectors |
| Switch-node copper | <100 mm² (<40 mm² near an edge or connector) |
| Hot loop | flagged from 30–40 mm² |

## Placement priority order
Source: [HS] §8.
1. Lock mechanicals, cluster connectors, mark the I/O zone.
2. Protection, filters, CMC, magnetics, chassis bond at the pins.
3. Interface ICs within ~2 cm, with a clear corridor.
4. Critical ICs (SoC, fly-by DRAM, SerDes): links short, uncrossed, direction-aligned, never between connectors.
5. Clocks next to consumers, away from I/O zone and edges.
6. Partition by function over one plane; power stages away from I/O.
7. In-line SI parts (series R at driver, AC caps), then decaps.

Steps 1–3 hard, anchor-relative; 4–6 soft costs (no primary source gives weights).

## Open questions
- Perimeter vs distributed stitching: Ott vs Hubing (CONTESTED).
- Ethernet ESD location: PHY side vs connector side (TI disagrees with itself).
- Missing primary numbers: TVS or CMC distance in mm; crystal-to-aggressor distance; RF-to-SMPS distance; placement-objective weights.
- Clemson MREMC reports and the Hubing EMI-source paper unreadable (TLS failure); algorithm above from the live calculator code.

## Sources
- [rules_highspeed_emi.md § 7, 8, 10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md); [verification_rules.md § 1A, 2, 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md); [interface_rule_packs.md § 9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
- LearnEMC hub: https://learnemc.com/emc-design-guidelines; TI SLVA680A: https://www.ti.com/lit/pdf/slva680
- See also [crystals-clocks.md](crystals-clocks.md).
