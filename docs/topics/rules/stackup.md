# Stackup selection

*Tags:*
- [P] primary source read
- [S] snippet
- [I] our inference
- VR statuses as in [si-fundamentals.md](si-fundamentals.md)

**TL;DR**
- **Ott's framework.**
  - Four factors: layer count, the number and type of planes, layer order, and spacing.
  - Five objectives:
    1. every signal layer adjacent to a plane;
    2. signals close to their planes;
    3. power and ground (P/G) tightly coupled;
    4. high-speed (HS) signals buried between planes;
    5. multiple ground planes.
  - Eight layers is the minimum that meets all five. Layers beyond eight are for routing only.
- **Hartley's two prohibitions:** never two signal layers on one plane, and never stacked power planes with no ground nearby. He also rejects thick 1.6 mm S/P/G/S and S/P/S/S/G/S stacks.
- **Experts disagree on two stacks.** Ott and Hartley disagree on the common 6-layer stack, and TI and Ott disagree on stripline for HS pairs. Both are **warnings with a selector**, not rejections.
- **Choose the stackup before placement.** It fixes each layer's reference plane, which vias change the reference, stub lengths, and the width and gap per layer.
- **Ship the candidate library below plus the 8-step scorer.** No primary source gives a scoring function, so the scorer is our synthesis [I].

## Key facts

### Ott ([Part 1](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-1.html) [P])
- **Layer count.** It is driven by signal count and cost, frequency, Class A or B, enclosure, and the team's EMC expertise.
- **Rules of thumb.**
  - A 4-layer board radiates 15 dB less than a 2-layer board [VERIFIED].
  - Go multilayer above 10–15 MHz.
  - Plane-pair capacitance is inadequate below about 500 MHz, so on 4- and 6-layer boards favour tight signal-to-plane coupling over P/G coupling.
  - There is "very little EMC advantage" above 8 layers [VR].
  - Keep the stack symmetric to avoid warp.
- **Signal-class assignment.** Assign clocks, buses, HS and low-frequency (LF) signals to specific layer pairs.

### Hartley ([Altium](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley) [P])
- **S/P/G/S at 1.6 mm.** The planes are about 1 mm apart, and every L1→L4 via is a P↔G reference change. It is acceptable only if the planes are no more than about 10 mil apart.
- **S/P/S/S/G/S.** "Even worse than the four layer."
- **Two or three power planes adjacent with no ground nearby.** "A very serious problem."
- **His own earlier recommendations.** He has disowned his older paper "Board Stack-up to Control EMI".

### Hubing ([LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines) [P; VERIFIED])
- No stackup guideline fits more than a small subset of boards.
- Assigning a whole layer to one circuit type is generally a bad idea.
- "Two ground planes above 25 MHz" is outdated.

### Candidate library
Source: Ott [P], annotated with Hartley; VR verified Figs. 3b, 6, 9 and 11.

| L | Stack (top→bottom) | Objectives met | Notes |
|---|---|---|---|
| 4 | S/G/P/S; signal–plane <0.010", core >0.040" | 1, 2 | 0.005" spacing gives ≥10 dB less loop radiation; crosstalk ∝ h². Hartley: avoid at 1.6 mm with fast edges |
| 4 | G/(S+P)/(S+P)/G; power as a wide-trace grid, grounds stitched around the periphery | 1, 2, 4, 5 | Ott: "best … four-layer" [VR FOUND]. Pads cut up the outer grounds |
| 4 | G/S/S/P | — | Shields the inner signals; rework is hard |
| 4 | (S+P)/G/G/(S+P) | 1, 2, 5 | Rework-friendly |
| 4 | S/S/G/S | 1 (L2 only) | Hartley's "worst": L1 and L2 share one plane |
| 6 | S/S/G/P/S/S | — | Ott: "NOT to use" |
| 6 | LF/G/HF/HF/P/LF | 1, 2, 4 | The most common stack. Ott: fine with careful decoupling. Hartley: "even worse". **Warn with rationale; do not reject** |
| 6 | H1/G/V1/H2/P/V2 (5/5/40/5/5 mil) | 1, 2 | Orthogonal pairs share a plane |
| 6 | G/S/G/P/S/G | all | Only two routing layers |
| 8 | LF/P/G/HF/HF/G/P/LF | all | GND–GND via at each L4↔L5 change |
| 8 | G/H1/G/V1/H2/P/V2/G (10/5/5/20/5/5/10 mil) | all | — |
| 8 | H1/G/V1/G/P/H2/G/V2 (6/6/15/6/15/6/6 mil) | 1, 2, 3, 5 | Tight P/G core; one of Ott's favourites |
| 8 | Six routing layers | — | "Definitely not recommended": use 10 layers |
| 10 | LF/G/HS/HS/P/G/HS/HS/G-or-P/LF | all | Clocks on one HS pair and buses on the other |

### Other inputs
- **LearnEMC** ([P](https://learnemc.com/other-good-emc-design-guidelines); [P](https://learnemc.com/pcb-layout))
  - If ≥3 power pins share a voltage, use a plane pair <0.25 mm apart, with HF decaps on the side nearest that pair.
  - Put power planes on one layer and never overlap them (balanced ±12 V excepted).
  - The gap between power planes must be ≥ the plane-to-ground spacing. VR adds ≥3 mm ("Maybe").
- **TI SPRAAR7J** ([P](https://www.ti.com/lit/pdf/spraar7))
  - At least six layers.
  - Adjacent signal layers at 90°.
  - HS pairs on the top or bottom layer over GND: "**TI does not recommend stripline**".
  - Split planes are allowed, but traces must not cross the splits.
  - Planes that do not reference each other must never overlap.
- **Ott's impedance rules of thumb (FR-4)** ([P](https://hott.shielddigitaldesign.com/techtips/rulesofthumb.html))
  - Microstrip Z0 is 60–70 Ω at w/h = 1 and 40–50 Ω at w/h = 2.
  - Stripline ≈ 0.6× microstrip; asymmetric stripline ≈ 0.75×.
  - Delay is 150 ps/in (microstrip) and 180 ps/in (stripline).
  - Dk is 4.0–5.0 (typically 4.5), and Z0 ∝ 1/√εr.
  - u-blox: 50 Ω microstrip width ≈ 2× the dielectric thickness [VR].
- **Johnson, crosstalk vs h.** Moving from 6 to 4 mil to the plane cut crosstalk by about 35% ([P](https://www.sigcon.com/Pubs/news/3_20.htm)). Before resorting to clock modulation, he prefers planes, small h, thin packages, slow edges, and differential or low-swing clocks.
- **Fibre weave.**
  - TI: rotate the image or the routing by 10–35°, or zig-zag. Prefer tight weaves (1080 and 2116 over 7628).
  - NXP: route long traces off-axis.
  - Sources: [SPRAAR7J p.3–5](https://www.ti.com/lit/pdf/spraar7); [NXP AN10373](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/powerquicc/2284/2/philips_PCIe_pcb_routing_guide.pdf) [P].
- **Reference stacks.**
  - HDMI retimers: L1–L2 of 5–10 mil on 4- and 6-layer boards ([TMDS181](https://www.ti.com/lit/ds/symlink/tmds181.pdf) [P]).
  - Espressif 4-layer: L2 is complete GND, L3 carries power plus a few signals [VR].
  - OSH Park 4-layer: FR408HR, L1–L2 7.87 mil, 39 mil core.
  - JLCPCB:
    - Dk: 4.5 (2-layer), 4.4 (7628), 4.1 (3313), 4.16 (2116).
    - Impedance ±10% (±5% on request).
    - Backdrill on 4–32 layers, ≥0.8 mm thick ([JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities) [P]).
- **Stubs and stackup.** Decide the stub strategy (backdrill, near-outer layers, blind/buried vias) before defining the stackup ([Telian](https://www.signalintegrityjournal.com/articles/2962-fixing-the-problem-of-stubs) [P]).

## Recommendations for our system

### Stackup selection algorithm ([I], synthesis)
1. Estimate the routing layers needed from pin density and BGA escape. If ≥6, go to 10 layers.
2. Decide whether objective 4 is needed, based on edge rates, emission class and enclosure.
3. Enumerate the library candidates for that layer count.
4. Reject candidates with:
   - a signal layer not adjacent to a plane (an Ott red flag);
   - two fast layers on one plane;
   - adjacent power planes with no ground.
5. Score the survivors:
   - start from the objectives met;
   - subtract a penalty for forced P↔G changes;
   - subtract plane-pair separation if ≥3 power pins share a rail.
6. Minimise h, subject to a manufacturable width at the target Z0. Take up the remaining thickness in the core and keep the stack symmetric.
7. Pair orthogonal layers that reference the same plane.
8. Field-solve the width and gap per layer, then emit per-layer net classes and per-layer delay into the KiCad 10 tuning profile.

### Other recommendations
- Store each layer's reference plane and the via spans that change reference. Return-path, via-stub and crosstalk checkers consume them ([checkers-si-emi.md](checkers-si-emi.md)).
- Store fab stack options (cores, prepregs) as data. This was not researched.

## Conflicts and open questions
- **Common 6-layer (LF/G/HF/HF/P/LF).** Ott says it is acceptable with careful decoupling; Hartley says it is "even worse". The selector should be plane separation and edge rate.
- **HS pairs: microstrip vs stripline.** TI says no stripline; Ott says bury HS signals (objective 4); TI SNLA426 and Efinix prefer coupled stripline at PCIe Gen4–5. TI does not explain its motive (possibly via stubs). VR: CONTESTED, so this needs a context switch.
- **Perimeter stitching.** Ott stitches the G/S/S/G periphery; LearnEMC warns this creates a cavity. See [emc-placement.md](emc-placement.md).
- **Open questions.**
  - Hartley's fix for the 6-layer stack is not in the transcript.
  - There is no quantitative stackup scoring function.

## Sources
- Research notes:
  - [rules_highspeed_emi.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)
  - [verification_rules.md § 1A, 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
  - [interface_rule_packs.md § 10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
- Ott stack-up parts 1–6: https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-1.html (through `-6.html`)

See also:
- [si-fundamentals.md](si-fundamentals.md)
- [diff-pairs.md](diff-pairs.md)
- [myths-and-contested.md](myths-and-contested.md)
- [dfm-fab-limits.md](dfm-fab-limits.md)
