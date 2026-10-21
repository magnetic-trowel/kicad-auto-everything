# EMC placement: radiation mechanisms, connector zoning, TVS/CMC, stitching, edges

*Tags:*
- [P] primary source read
- [S] snippet
- [I] our inference
- VR statuses as in [si-fundamentals.md](si-fundamentals.md)

**TL;DR**
- **The radiators are the cables and the chassis.** Below about 100 MHz they are the only efficient antennas. About **1 mV between two cable reference points can fail Class B** (100 µV under stricter limits). So EMC placement means never letting a voltage develop between connectors.
- **Connector placement:** all cabled connectors on one edge or one corner, no high-speed circuitry between connectors, I/O devices within about 2 cm of their connector, other parts at least 2 cm away. These are LearnEMC defaults, labelled "situational".
- **Protection parts** are best written as **comparative topology constraints**: connector → TVS → IC, with no via or stub before the TVS and a GND via right at the TVS pad. TI gives no millimetre value. The "TVS within 5–10 mm" and "CMC within 5 mm" figures are soft.
- **Edges:** keep high-speed traces ≥90 mil from the reference-plane edge (TI) and ≥2h from the board edge (LearnEMC). Plane edges need a zone-aware check, because `edge_clearance` covers only Edge.Cuts.
- **Stitching is contested.** Perimeter rings versus distributed vias is unresolved, and no primary source gives λ/20 or 3–5 mm. Measure the largest unstitched region instead. Rank findings by estimated common-mode voltage, not by rule count.

## Key facts

### Radiation mechanisms and thresholds

**Antenna model** ([LearnEMC](https://learnemc.com/pcb-layout) [P; VERIFIED])
- An unintentional antenna needs two parts that are not electrically small, with a voltage between them.
- Below about 100 MHz, only cables and chassis qualify.
- Above 100 MHz, tall parts, heatsinks, seams and sparsely populated planes also qualify. ICs, traces and dense planes are poor antennas.
- Hold antenna parts within 1 mV of each other, or 100 µV for limits stricter than CISPR 32 B.

**Magnetic coupling between connectors**
- Return flux wraps the plane: "tens of mA at tens of MHz" induces millivolts, more with wider and higher traces. Stripline induces nothing.
- Fixes: put connectors on one edge, or bond the chassis to the plane at both connectors.

**MREMC common-mode algorithm** ([CMode_algr.js](https://learnemc.com/ext/calculators/mremc/calculator/CMode_algr.js) [P], Hubing/Su/Zhu)
- Return-plane inductance: L_ret = (µ0/π)·t·l_t/w_e/√(1 − 4(1 − 2t/w_e)·offset²/w_e²), where w_e = d1 + d2 (the distances to the two board edges) and offset = |d1 − d2|/2.
- Trace inductance: L_trace = √(µ0ε0)·l_t·Z0. Imbalance: h = L_ret/(L_ret + L_trace).
- Common-mode voltage:
  - voltage-driven: V_cm = h·V_dm;
  - current-driven: V_cm = 2πf·L_ret·I_dm, with I_dm = V/R_L or V·2πf·C_L.
- Field: E_max = F_max·0.55·V_cm·boardfactor·cablefactor.
  - boardfactor = sin(2πL_eff/λ) when λ ≥ 4L_eff, else 1.
  - cablefactor = sin(2π·1 m/λ) when λ ≥ 4 m, else 1.
  - F_max = 2/sin(√(c/(f·L_cable))) above the cable half-wave resonance.
- L_eff depends on which side of the trace each cable connector sits.
- Assumes no shielded enclosure, a cable much longer than the board, and a height of about 1 m above ground.
- References: Su & Hubing 2011 (IEEE T-EMC 53); Zhu & Hubing, CVEL-13-051.

**emcvisual simplifications** ([RULES.md](https://github.com/tombueng/emcvisual/blob/main/docs/RULES.md) [P])
- Cable common mode: L_p = (4/π²)µ0·l·h/(d1 + d2), V = ωL_p·I, E = 0.365·V (Hockanson/Hubing 1996).
- I/O coupling: M = µ0/(4π)·ln(1 + 4h²/s²), E = 40·V/Z_ant, with Z_ant = 80(N+1) Ω.

**Ott's formulas** (via kicad-happy; secondary to Ott's book) ([MIT](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md) [P])
- Differential-mode loop: E = 2.632×10⁻¹⁴·f²·A·I/r.
- Common-mode cable: E = 1.257×10⁻⁶·f·L·I_CM/r.
- Doubling the loop area adds 6 dB; doubling the frequency adds 12 dB.

**Cable common-mode current limits**
- Ott: <5 µA for Class B and <15 µA for Class A, for cables ≥1 m (10 µA at 0.5 m).
  - Measure with a clamp probe (F-33-1, 2–250 MHz) and iterate over every cable, because fixing one cable can raise another ([Ott](https://hott.shielddigitaldesign.com/techtips/tips-cm.html) [P]).
- Hartley: 8–10 µA fails Class B.

**FCC §15.109** ([CFR](https://www.law.cornell.edu/cfr/text/47/15.109) [P])

| Class | Distance | 30–88 MHz | 88–216 MHz | 216–960 MHz | >960 MHz |
|---|---|---|---|---|---|
| B | 3 m | 100 µV/m | 150 µV/m | 200 µV/m | 500 µV/m |
| A | 10 m | 90 µV/m | 150 µV/m | 210 µV/m | 300 µV/m |

**Consistency checks** [I]
- Ott's common-mode formula with a 1 m cable at 3 m and 150 µV/m (100 MHz) gives about 3.6 µA, consistent with his 5 µA limit.
- MREMC with V_cm = 1 mV predicts about 61 dBµV/m, roughly 20 dB over Class B. That is why 1 mV is a hard line.

**Other mechanisms**
- Cavity resonance: f_mn = (c/2√εr)·√((m/L)² + (n/W)²), independent of plane spacing ([LearnEMC calc](https://learnemc.com/ext/calculators/cavity_resonance/pcb-res.html) [P]).
- Treat every pin of a fast-clocked IC as an HF source. Near-field scans show DRAM supply pins carry more current than its signal pins (LearnEMC).

### Connector zoning ([LearnEMC good guidelines](https://learnemc.com/other-good-emc-design-guidelines) [P; VERIFIED, with numeric defaults added by VR])
- Put cabled connectors on **one edge or one corner**.
- **No HS circuitry between connectors.** Guideline #3 calls this "one of the most common problems". If unavoidable, use a metal chassis bonded at both connectors.
- Put each I/O device **within about 2 cm** of its connector, and route each device's off-board links through one connector.
- Keep non-I/O parts **≥2 cm** from I/O nets and connectors. LearnEMC: "not necessarily the best advice in every situation".
- Route no unrelated trace between a connector and its device, and no HF signal under I/O components.
- Place clock drivers next to their oscillators, and place parts that talk only to each other together.
- Minimise vias on HF nets. Tie unused digital inputs high or low.
- **Worst guideline:** "group by type, HS farthest from the connector" ([LearnEMC worst](https://learnemc.com/some-of-the-worst-emc-design-guidelines)). Instead, put the parts that talk through a connector next to it.

### I/O nets, filters, protection ([LearnEMC PCB Layout](https://learnemc.com/pcb-layout) [P])
- Each I/O net should end in a series or filter component near the connector. An IC that drives a cable directly must not inject more than about 1 mV of common mode.
- Mount filters with minimal parasitics, and avoid higher-order filters that ring.
- A CMC must filter a **balanced** pair. **Never put a ferrite on ground.**
- Protection for an IC goes to that IC's ground; protection for the board goes to the EMC ground. Connection inductance is critical.
- Metal enclosure: send ESD current to the enclosure without pulling it onto the board. Plastic enclosure: check for arc paths through seams, and slow high-impedance inputs with resistors.

### TVS topology ([TI SLVA680A](https://www.ti.com/lit/pdf/slva680) [P]; VR: topology VERIFIED, mm distance NOT FOUND)
- Place the TVS "as near to the connector as design rules allow". Place the protected IC "much further from the TVS than the TVS is to the connector".
- No stubs, and no via between the ESD source and the TVS. If a via is unavoidable, route source → TVS first, then the via (Case 1). Avoid Case 2, where the IC branch comes before the via.
- **Why it matters:** an 8 kV strike gives dI/dt = 4×10¹⁰ A/s, so **0.25 nH of extra inductance adds 10 V** at the IC.
- **Corners on the strike path:** a 90° corner develops ≥7 kV and arcs at radii below **about 2.6 mm**. Use curves, with 45° as the maximum. Treat the area as a keep-out for unprotected traces.
- **TVS ground:** one via **immediately adjacent** to the GND pin, into a same-layer plane that couples to an adjacent plane.
  - TI's example uses 4 stitching vias plus a chassis screw.
  - BGA-TVS example via: 0.254 mm pad, 0.152 mm drill, epoxy-filled and plated over, 0.1 mm clearance.
  - Make GND vias as large as possible.
- The **5–10 mm TVS distance comes from blogs**, so it is a soft target. emcvisual flags a diode that sits nearer the IC than the connector, or one with no ground pour or via within 2 mm.
- Ethernet is an exception: TI SNLA387 puts ESD on the PHY side of the magnetics. See [interfaces/ethernet.md](interfaces/ethernet.md).

### CMCs and filters
- TPS case study: a CMC more than 30 mm from the DC input failed CISPR 25 Class 5; moved **within 5 mm**, it passed ([TPS](https://tps-elektronik.com/en/case-studies/how-to-pass-automotive-conducted-emissions-cispr-25-class-5-with-tps-split-ground-plane-and-common-mode-choke-placement-emc-layout-guidelines-for-automotive-dc-dc-converters/) [P; VERIFIED case study, medium authority]).
- TI: put AC caps on the protected side of the CMF; use a 0402 0 Ω no-stuff footprint as an alternative to the CMF.
- emcvisual flags a ferrite, inductor or shunt cap on a cable line more than 10 mm from the connector pin.
- CAN: protection belongs in the signal path ([interfaces/can-rs485.md](interfaces/can-rs485.md)).

### Edges (VR closed this gap with three primary numbers)

| Rule | Value | Source |
|---|---|---|
| Distance from reference-plane edge | ≥90 mil (2.29 mm) for HS differential pairs | [TI SPRAAR7J p.9](https://www.ti.com/lit/pdf/spraar7) [P] |
| Distance from board edge | ≥2X, where X = distance from trace to its return | [LearnEMC](https://learnemc.com/other-good-emc-design-guidelines) [P] |
| Distance from GND-plane edge | >3W | [u-blox NORA-B2](https://content.u-blox.com/sites/default/files/documents/NORA-B2-u-connectXpress_SIM_UBXDOC-465451970-3906.pdf) [P] |
| Others | TI Gen5: ≥5·max(W,H). Microchip: SS ≥5W from plane edges and splits, with narrow floods via'd at corners and ends. Pulse: more than the trace height; Ethernet PHY ≥25 mm from the edge. Ours: centreline ≥ w/2 + 3h | IF §9 [P]; HS [I] |
| Thresholds in existing checkers | kicad-happy < h (outer layers); EMI Guardian 1 mm; emcvisual <3h (≥1 mm) over ≥3 mm | [P] code |
| Edge guard band | A plane-copper guard band along the edge was the most effective suppression of edge-driven common mode | [ResearchGate](https://www.researchgate.net/publication/3056626_Common-Mode_Current_Due_to_a_Trace_Near_a_PCB_Edge_and_Its_Suppression_by_a_Guard_Band) [S] |

### Stitching (CONTESTED)
- **Perimeter vs distributed.** Ott stitches the two grounds of a G/S/S/G board around the periphery as a Faraday cage. LearnEMC rates "perimeter vias every 2 cm" not-so-good: usually unnecessary, and a perimeter-only ring "will create a resonant cavity", so distribute the vias instead ([LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines)).
- **No primary source gives λ/20 or a 3–5 mm stitching pitch.** λ/20 is Ott's *aperture* red flag: 6" at 100 MHz.
- **Split boundaries:** TPS case study, stitch every **10–15 mm**. The design failed at 40–50 mm and passed at 12 mm. "Above 100 MHz the slot … acts as an effective antenna" [VERIFIED, medium authority, soft].
- **Other figures:**
  - Johnson: a via row at about ¼" pitch, and a 10:1 signal:ground via ratio.
  - u-blox: a stitched GND ring at the board edge, with power planes kept back from it.
  - KiCad master `PCB_VIA_STITCH`: default pitch max(2 mm, 2× via diameter).

### Grounding and chassis
- **One ground.** Hubing 2019 lists "more than one ground" as MOST EGREGIOUS and calls for "1 solid ground plane under all digital logic" ([slides](https://r6.ieee.org/scv-emcs/wp-content/uploads/sites/111/022019ToddHubing.pdf) [P]). Clearing ground under magnetics, inverters or HV is fine; gapping it is not.
- **Chassis bonding:** a chassis layer *overlapping* digital ground, bonded with multiple SMT caps, plus one low-frequency connection. The goal is low impedance above 30 MHz and isolation below about 100 kHz.
  - Never a single-point bond at the I/O by default, and never at the oscillator.
  - "Bond (at RF) everything that leaves the board." Near metal structure: "Connect to it!"
- **Mixed signal (Ott)** ([P](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html)):
  - One plane, partitioned, with routing discipline on all layers.
  - LSB at a 1 V reference: 8-bit 4 mV, 10-bit 1 mV, 12-bit 240 µV, 14-bit 60 µV, 16-bit 15 µV.
  - At ≥14 bits: isolated regions solidly joined under each ADC, with no trace on any layer crossing the slots.
  - Experiment: split the plane with 0 Ω jumpers every ½", then compare.
- **Power stages (LearnEMC):** keep switch-node area minimal and away from conductors; mind the switching-loop magnetic coupling. Switch modern DC-DC converters in the MHz range, with no isolated power grounds. Transitions longer than about 1% of the switching period cost efficiency. See [power/buck.md](power/buck.md).
- **Deliberate splits only:**
  - MT-031: more than 300 mV between planes risks latch-up.
  - The DA9080 PMIC mandates GND cuts between its bucks, so the rules need a datasheet override [VR].

### Pre-compliance practice
- **LearnEMC 10-step review.** Hold it before layout and again at the first draft:
  1. ground structure and I/O;
  2. plane extent, with no gaps;
  3. ground traces and fills (remove them);
  4. power on a plane pair <0.25 mm apart;
  5. I/O nets;
  6. filters;
  7. transition times;
  8. critical parts (op-amp loops over the plane, PLL ferrites, no ferrite on ground);
  9. power inverters;
  10. each test's current path (CE, RE, BCI, RI, EFT, ESD).
- Include **footprints for optional filters, TVS and shields**.
- "Blindly adhering" to EMC rule lists fails. Identify sources, victims and coupling paths instead ([LearnEMC](https://learnemc.com/effective-application-of-emc-design-guidelines)).
- **Johnson** ([emisim](https://www.sigcon.com/Pubs/edn/emisim.htm)):
  - Simulators cannot handle real EMI; useful tools are "more like expert systems".
  - "2× last year's design needs another 6 dB."
  - Run an EMI preview scan early.
- **Hubing's seven common errors:**
  1. blindly following guidelines;
  2. uncontrolled transition times;
  3. not following currents;
  4. not identifying critical traces;
  5. more than one ground;
  6. improper decoupling;
  7. bypassing filters.
- **Ott's red flags** ([P](https://hott.shielddigitaldesign.com/techtips/red_flags.html)):
  - clock edges <10% of the period;
  - apertures >λ/20;
  - split grounds;
  - traces crossing slots;
  - pigtail shields;
  - backshells not contacting the enclosure;
  - paint in seams;
  - signal layers not adjacent to a plane;
  - parallel decaps of multiple values;
  - ungrounded fill or thieving;
  - unshielded, unfiltered cables;
  - a single-point circuit-to-chassis bond.
- **Ott's satirical "maximize emission" list**, inverted, is worth 20–30 dB ([P](https://hott.shielddigitaldesign.com/techtips/maxemission.html)). Inverted, it says:
  - avoid fast edges below 1 ns;
  - keep clocks off the board edge and out of the I/O area;
  - no slots;
  - no clock traces across isolated grounds;
  - more than one decap per IC;
  - I/O filters at the cable entry;
  - no pigtails;
  - bond logic ground to chassis at the I/O;
  - no painted seams;
  - the AC filter at the cord entry.
- **Ott:** for buried planes, ask the fab for one etched-but-unlaminated set.
- **kicad-happy pre-compliance outputs** [P]:
  - band prioritisation by emission-source count;
  - interface risk ranking;
  - XY near-field probe points;
  - a 0–100 risk score capped at 3 findings per rule.

### emcvisual placement thresholds [P]
| Part or feature | Threshold |
|---|---|
| Crystal | ≥5 mm from the edge, ≥10 mm from cable connectors |
| Storage inductor | ≥3 mm from the edge, ≥10 mm from cable connectors |
| Switch-node copper | <100 mm² (<40 mm² near an edge or connector) |
| Hot loop | flagged from 30–40 mm² |

### Placement priority order ([HS] §8)
1. Lock mechanicals, cluster the connectors and mark the I/O zone.
2. Place protection, filters, CMC, magnetics and the chassis bond at the pins.
3. Place interface ICs within about 2 cm, with a clear corridor.
4. Place critical ICs (SoC, fly-by DRAM, SerDes) so links are short, uncrossed and direction-aligned, and never between connectors.
5. Place clocks next to their consumers, away from the I/O zone and edges.
6. Partition by function over one plane, with power stages away from I/O.
7. Place in-line SI parts (series R at the driver, AC caps), then decaps.

Steps 1–3 are hard, anchor-relative constraints. Steps 4–6 are soft costs; no primary source gives weights.

## Recommendations for our system
- **Placer costs:**
  - the MREMC "between connectors" V_cm estimate ([checkers-si-emi.md](checkers-si-emi.md) checker F);
  - I/O-zone intrusion;
  - fast-net length and crossings;
  - pair direction alignment;
  - crystal, inductor and switch-node distance to edges and connectors (emcvisual thresholds).
- **Write TVS and CMC rules as comparative constraints:** d(TVS, connector) < d(TVS, IC), zero vias before the TVS, and a GND via at the TVS pad. Never use millimetre DRC errors for these.
- **Edges per layer:**
  - `edge_clearance` ≥2h for fast classes;
  - a geometric check for ≥90 mil (or w/2 + 3h) from plane edges;
  - keep-out rule areas for the I/O zone.
- **Stitching:** use a single "largest unstitched region" metric, which avoids settling the perimeter-vs-distributed debate. Use KiCad master's GUARD generator for fences.
- **Optional footprints:** always add them (CMF 0 Ω, TVS, shield-can pads, chassis R/C) when compliance is uncertain.
- **Ranking:** order findings by estimated V_cm or I_CM, not by number of violations.

## Conflicts and open questions
- **Perimeter vs distributed stitching:** Ott vs Hubing (CONTESTED).
- **Ethernet ESD location:** PHY side vs connector side (TI disagrees with itself).
- **Missing primary numbers:**
  - TVS or CMC distance in mm;
  - crystal-to-aggressor distance;
  - RF-to-SMPS distance;
  - placement-objective weights.
- **Unread sources:** the Clemson MREMC reports and the Hubing EMI-source paper were not readable (TLS failure). The algorithm above comes from the live calculator code.

## Sources
- Research notes:
  - [rules_highspeed_emi.md § 7, 8, 10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)
  - [verification_rules.md § 1A, 2, 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
  - [interface_rule_packs.md § 9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
- LearnEMC hub: https://learnemc.com/emc-design-guidelines
- TI SLVA680A: https://www.ti.com/lit/pdf/slva680

See also:
- [si-fundamentals.md](si-fundamentals.md)
- [checkers-si-emi.md](checkers-si-emi.md)
- [myths-and-contested.md](myths-and-contested.md)
- [crystals-clocks.md](crystals-clocks.md)
- [power/buck.md](power/buck.md)
