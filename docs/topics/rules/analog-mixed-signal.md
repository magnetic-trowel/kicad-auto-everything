# Analog and mixed-signal layout: grounding, ADC/DAC AGND/DGND, guards, op-amp nodes

Scope: analog/digital grounding by ADC resolution, ADC/DAC AGND/DGND, splits and bridges, guards, op-amp summing nodes, thermal EMF, AMS rule IDs. Not here: sensor front ends -> [precision-sensing.md](precision-sensing.md); crystals -> [crystals-clocks.md](crystals-clocks.md); LF audio grounding -> [power/class-d-audio.md](power/class-d-audio.md).
Keys: mixed signal, analog ground, AGND, DGND, split ground, ground plane partition, ADC, DAC, LSB table, MT-031, SLYT512, guard ring, driven guard, AN-241, summing node, IN−, thermal EMF, common centroid, matched pairs, AMS-01, AMS-09

## Mixed-signal grounding rules
1. One solid ground plane, partitioned in placement and routing so analog and digital returns never share a region; ADCs straddle the boundary (Ott, TI). Do not split; if forced, one bridge with every crossing over it.
2. Ground strategy is rule-selected from ADC bits (BOM) + datasheet mandates: single partitioned plane for 8–12 bits; isolated regions tied under each converter at ≥14 bits (no trace on any layer crossing the slots); bridged split only when mandated. Each choice activates its checks (slot-crossing detector, net-tie count, 300 mV inter-plane check, Schottky clamp suggestion).
3. Low-digital-current ADCs/DACs are analog parts: AGND and DGND to the analog plane at the package "even if the data sheet suggests otherwise" (ADI); exception: multi-converter parts that specify their own scheme.
4. Guard high-Z inputs with a ring driven at the node's potential, both sides; minimise summing-node copper (1 pF across 1 kΩ → severe peaking, Williams).
5. Below ~100 kHz returns spread resistively: engineer return paths ([power/class-d-audio.md](power/class-d-audio.md)).
6. Region partitioning -> [placement-methodology.md](placement-methodology.md#placement-methodology-rules). Criticality map entries for summing nodes, guard nets, matched pairs ([checkers-power.md](checkers-power.md#criticality-map)). Matched pairs: mirror-symmetry / common-centroid metric + distance to estimated heat sources.

## Ott on split grounds and LSB budget
Source: ([tech tip](https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html)) [P]:
- Routing across a split gives the return no nearby path, so it radiates and adds ground inductance. Prefer one plane, partitioned, with ADCs straddling.
- If a split is required, connect at one bridge and route all crossings over it.
- LSB at a 1 V reference (scale by V_ref): 8 bit 4 mV; 10 bit 1 mV; 12 bit 240 µV; 14 bit 60 µV; 16 bit 15 µV; 20 bit 1 µV; 24 bit 60 nV. Keep analog ground noise below the smallest signal.
- 8–12 bits: one partitioned plane is "usually adequate".
- ≥14 bits: "separate isolated analog and digital ground plane regions, each solidly connected to the digital ground plane under each of the A/D converters … no traces, on any layer, can cross over the isolating slots".
- Test: lay out the split with jumpers or 0 Ω links every ½ inch and compare open vs closed; "in almost all cases … better with the single ground plane".
- On datasheet "AGND+DGND to the analog plane" advice: where does digital decoupling return? Use one plane from the start.

## TI on one ground plane
[P]
- "It is always preferable to use only one ground plane"; the main risk is analog routed into the digital section ([SLYT512](https://www.ti.com/lit/an/slyt512/slyt512.pdf)).
- Join AGND/DGND externally to the same low-impedance plane with minimum lead length ([SLYT499](https://www.ti.com/lit/pdf/SLYT499)).

## ADI MT-031 converter grounding
Rev A ( [PDF](https://www.analog.com/media/en/training-seminars/tutorials/MT-031.pdf)) [P], VERIFIED with nuance:
- Low-digital-current converters "should generally be treated as analog components … grounded and decoupled to the analog ground plane".
- "Connecting DGND to the digital ground plane applies VNOISE across the AGND and DGND pins and invites disaster!"
- Bryant (ADI co-author, [Grounding ADCs & DACs](https://www.hit.bme.hu/~papay/edu/Acrobat/GndADCs.pdf)): do this "**even if the data sheet suggests otherwise**".
- VD decoupling 0.01–0.1 µF to DGND, plus an optional small lossy bead.
- Buffer register adjacent to the converter outputs, with series R (example 500 Ω × 10 pF → t_r ≈ 11 ns).
- ~0.2 pF unavoidable stray capacitance between every pin of the package.
- "More than 300 mV between the two ground planes" can damage ICs, cause false triggering or latch-up. Use back-to-back Schottkys between separate AGND/DGND planes at the star.
- ADI EngineerZone [S]: multi-device datasheets (e.g. AD5522) specify their own scheme, and the eval-board layout comes first.

## Hubing and Pease on grounds
- Hubing / LearnEMC [P]: "more than one 'ground'" MOST EGREGIOUS ([emc-placement.md](emc-placement.md#grounding-and-chassis)); ground islands under ICs are "a bad idea".

- Pease (Lab Notes, [PDF](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/1023/Bob-Pease-Lab-Notes-Part-7.pdf)) [P]:
- For high analog/digital isolation, build the sections separately (analog possibly in a shielded box) and be prepared for copper fences, walls and screens.
- 35 dB rejection is feasible; 50 dB "will probably take all those extreme efforts".
- On the bench, use a grounded copper-clad sheet as a ground plane.
- "More than 50 rules for making transistors and resistors that match"; common-centroid "is usually very easy, using the rules of symmetry".

## Guards
Source: ([TI AN-241](https://www.ti.com/lit/an/snoa664/snoa664.pdf)) [P]:
- Drive the guard from a low impedance at the inputs' potential: tie to +IN for inverting, −IN for non-inverting ([Microchip](https://developerhelp.microchip.com/xwiki/bin/view/products/amplifiers-linear/operational-amplifier-ics/precision-design/leakage-currents/); [ADI](https://www.analog.com/en/resources/technical-articles/layout-for-precision-op-amps.html) [S]).
- Guard ring on both sides. Surface leakage "virtually eliminated"; bulk-leakage reduction "about an order of magnitude" with double-sided guarding.
- **"No solder mask over the guard" is not in AN-241**; the pages stating it were NOT RETRIEVABLE.
- Guard-gap numbers (0.5 mm, 50 mil) appeared only on low-authority sites and are excluded.

## Op-amp nodes and thermal EMF
- The inverting summing node is the most parasitic-sensitive ([Op Amps for Everyone](https://web.mit.edu/6.101/www/reference/op_amps_everyone.pdf)) [P].
- Williams AN47 ([mirror](https://www.mit.edu/~6.331/an47fa.pdf)) [P]: 1 pF across 1 kΩ caused severe peaking; "Minimize trace area and stray capacitance at critical nodes. Consider layout as an integral part of the circuit"; ground planes exist to minimise inductance (10 nH at 100 MHz = 6 Ω).
- Thermal EMF ~200 nV/°C at dissimilar-metal junctions; use symmetric layouts so paired junctions share a temperature ([Electronics360](https://electronics360.globalspec.com/article/9981/pcb-layout-for-precision-operational-amplifiers)) [V].

- Crystals -> [crystals-clocks.md](crystals-clocks.md). AMS-08 heuristic: crystal ≤~5 mm, symmetric caps, guarded (no primary mm value; ST AN2867 gives none). [I] ST's dedicated oscillator ground island sits uneasily with Hubing's "islands are a bad idea".

## Mixed-signal rule IDs
RPA §4 [I].

| ID | Rule | Numeric | Check | Class |
|---|---|---|---|---|
| AMS-01 | One continuous plane; analog/digital regions; ADC straddles with analog pins facing analog | No slots under signals | Region polygons from schematic blocks; cross-region tracks; void crossings | S2 |
| AMS-02 | AGND+DGND to the analog plane at the package, for low-digital-current converters (MT-031) | Via at the pad | Net or net-tie at the package | Hard (S1); escape only for scheme-specified multi-converter parts |
| AMS-03 | If split (datasheet-mandated): one bridge at the converter, crossings over it | Exactly one tie | Net-tie count; crossing tracks inside the bridge polygon | Hard (S1) |
| AMS-04 | Converter decoupling to analog ground at the pins; digital interface buffered/series-terminated near the converter | — | PDN-01 with an AGND reference | S2 |
| AMS-05 | Guard ring around ≥GΩ, electrometer or photodiode-TIA inputs | Ring encloses the input pin and the R_F high-Z end | Ring net = guard net | S1 for those circuits |
| AMS-06 | Feedback/input resistors at IN−; minimal summing-node copper | ≤~3 mm [I] | Total copper on IN− nets | S2 |
| AMS-07 | Precision parts symmetric, away from heat | Isotherm symmetry | Distance to hot parts; mirror-symmetry metric | S2 (<100 µV error systems) |
| AMS-09 | Kelvin on all precision sense points | — | [power/current-sense-kelvin.md](power/current-sense-kelvin.md) | S1 |

## Open questions
- **"Always split AGND/DGND"** is largely legacy datasheet text (Ott, TI). Splitting is a context switch, used only when mandated.
- **AMS-02's datasheet escape** conflicts with ADI's own guidance; keep it only for scheme-specified parts.
- **No numeric thermal-gradient budget for references** was found.

## Sources
- [rules_power_rf_analog_dfm.md § 4, § 16, § 19](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B, § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also: [precision-sensing.md](precision-sensing.md), [crystals-clocks.md](crystals-clocks.md), [decoupling-pdn.md](decoupling-pdn.md), [power/class-d-audio.md](power/class-d-audio.md)
