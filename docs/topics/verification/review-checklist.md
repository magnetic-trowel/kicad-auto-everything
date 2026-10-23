# Layout review checklist: structure, Critical items and top Major items

**TL;DR**
- About 30 checklists and guides merge into **299 distinct layout-review items in 24 categories**: 41 Critical, 151 Major, 107 minor.
- By automation class, about 37% are pure geometry/DRC checks, about 41% need net and part semantics, and about 22% need judgment, external data or simulation. Of the 41 Critical items, 80–83% are at least semi-automatable, depending on how the mixed tags count.
- The biggest automation enabler is a **semantic annotation layer**: part roles, net roles, currents, voltages, frequencies and datasheet thresholds.
- Thresholds conflict between sources, so they must load from fab and assembler profiles, never from hard-coded values.
- The full item list is split across five `checklist-full-*.md` files (see See also). Source keys are defined in [checklist-sources.md](checklist-sources.md).

## Key facts

Tags: [P] primary; [I] inference. Severity and automation tags are the source note's assignments, based on each source's rationale [I].

### Structure and statistics

| Category | Items | Category | Items | Category | Items | Category | Items |
|---|---|---|---|---|---|---|---|
| Process | 18 | Power conversion | 9 | EMC/ESD | 10 | Assembly | 13 |
| DFM | 27 | Ground/return | 13 | Thermal | 6 | Test/debug | 13 |
| Stackup | 12 | High-speed | 24 | Footprints | 13 | Silkscreen | 14 |
| Mechanical | 21 | RF | 6 | Routing | 11 | HV/safety | 3 |
| Placement | 27 | Analog | 4 | Zones | 7 | Outputs | 13 |
| Power integrity | 15 | Flex | 7 | Paste/mask | 5 | Panel | 8 |

**Severity**: C = 41, M = 151, m = 107. **Automation class** (primary tag):

| Class | Items | Of the 41 Critical |
|---|---|---|
| A | 101 | 19 |
| A/S | 9 | 0 |
| S | 119 | 14 |
| S/J | 4 | 1 |
| J | 66 | 7 |

The S/J row includes the one J/S item, PLC-27, which is also its only Critical item. Counted under its primary tag J, the semi-automatable Critical share is 33/41 = 80% instead of 34/41 = 83%. PRC-04 (A + J) and PWR-01 (S + J/sim) are counted under their first tag.

Class meanings:
- **A**: geometry or DRC only.
- **S**: semi-automatic; needs roles or datasheet parameters.
- **J**: judgment, external information or simulation.

Thresholds conflict across sources:
- silk height: 25 mil (Sierra), 1.0 mm (PCB Power), 50 mil (UWARG);
- copper-to-edge: 8 mil (SparkFun) vs 10 mil (Sierra);
- part-to-edge: 125 mil (Sierra) vs 5 mm (Flux).

### All 41 Critical items

DRC keys are the KiCad 10 `type` keys verified in the KiCad-tools verification note.

| ID | Category | Check | Why | Auto |
|---|---|---|---|---|
| PRC-01 | Process | Schematic review signed off before layout; pin/gate swaps back-annotated and re-reviewed | Errors carry forward | S (parity A; sign-off J) |
| PRC-02 | Process | Board/schematic parity: no missing, extra or duplicate footprints; pad nets and attributes match | LVS | A (`missing_footprint`, `extra_footprint`, `duplicate_footprints`, `net_conflict`, `footprint_symbol_mismatch`) |
| PRC-03 | Process | Zero unrouted connections; no polygon breaks ("not unusual for a PCB to be sent to manufacturing without all the parts placed and routed") | Open nets | A (`unconnected_items`) |
| PRC-04 | Process | DRC 100% clean; every exclusion/waiver inspected and signed off | Waivers hide defects | A + J |
| PRC-05 | Process | Rules set from fab/assembler capability before layout; use the CM's own DRC file | DRC is only meaningful against real limits | S → A |
| PRC-12 | Process | ERC/DRC severity overrides, exclusions and "ignore" settings audited before trusting a clean result | "Anything on 'ignore' makes a clean pass hollow" | A (read severities, `ignored_checks[]`) |
| DFM-02 | DFM | Annular ring ≥ fab/IPC-class minimum (Pikafu: 5 mil Class 2 / 7 mil Class 3 for 10 mil vias; AllPCB: >3 mil) | Drill breakout | A (`annular_width`) |
| DFM-03 | DFM | Hole-to-hole and hole-to-copper clearance (inner and outer) | Breakout, shorts | A (`hole_clearance`, `hole_to_hole`) |
| DFM-11 | DFM | PTH ≥ lead + ~0.2 mm; square pins sized by diagonal; pad ≥ hole + 10–15 mil; soldered holes plated | Parts won't insert | S |
| DFM-21 | DFM | No overlapping or co-located drills; PTH and NPTH separated | Broken bits, voids | A (`holes_co_located`) |
| STK-01 | Stackup | Stackup (materials, dielectrics, copper, finished thickness) verified with the fab | Impedance, manufacturability | J |
| STK-09 | Stackup | Every controlled-impedance net matches a net-class pattern; nets matching none silently get Default (e.g. USB D+/D−) | Silent impedance miss | A (class-coverage report) |
| STK-12 | Stackup | Stackup drawing in fab docs; impedance written as "Layer N: Z ±tol, referenced to Layer M" | Top hold cause in one vendor's data | J |
| MEC-01 | Mechanical | Outline, dimensions and holes match the enclosure (3D, accurate models) | Board doesn't fit | S (MCAD) |
| MEC-04 | Mechanical | Off-board connectors match the mating standard (orientation, keying, pin 1, FPC contact side); pinout reversed if connectors face each other | Mis-mating | J |
| MEC-08 | Mechanical | No collisions or courtyard overlaps | Unassemblable | A (`courtyards_overlap`) |
| MEC-15 | Mechanical | Board thickness (and at card-edge connectors) specified and matching | "you'd be surprised how often this is overlooked" | J |
| MEC-17 | Mechanical | Board-to-board connectors spaced and located for mating | Mating | S (3D) |
| PLC-27 | Placement | Power stage: IC → input cap (placed and routed immediately, on the IC's layer for integrated converters; vias and plane coverage are scored through the loop-inductance estimate, and vertical loops to the first inner plane are allowed, [../rules/power/hot-loops.md](../rules/power/hot-loops.md)) → inductor/diode → output cap → small-signal → single-point ground | Hot loop dominates | J/S |
| PDN-05 | PI | Every IC power/ground pin connected; ground pins have vias to the plane | Floating supplies | A (parity + connectivity) |
| PDN-06 | PI | Trace/plane widths sized for current and temperature rise | Burn-out, IR drop | S (per-net current) |
| PDN-13 | PI | Width computed for every track >100 mA from IPC-2221/2152; internal-layer values if airflow is poor. Flux's "~10 mil/A on 1 oz external at 10 °C rise" holds only near 1 A: IPC-2221 is non-linear (≈12 / 31 / 54 / 109 mil at 1 / 2 / 3 / 5 A), and inner layers need ≈2.6× the external width, not 2× (our arithmetic on the IPC-2221 formula in verification_rules.md, catalog row PDN-07) [I] | Overheating | S |
| PWR-01 | Power conv. | Switching hot loop of minimal area | High di/dt loop radiates | S + J/sim |
| PWR-07 | Power conv. | Connectors and regulators current-rated in the chosen package | Overheating | J |
| GND-02 | Ground | HS nets don't cross splits/slots/voids; else stitching caps (TI: ≤1 µF at the crossing) or vias | Return detour acts as an antenna | S |
| HS-01 | High-speed | Diff pairs coupled at impedance gap; uncoupled length limited | Mode conversion | A (`diff_pair_gap`, `diff_pair_uncoupled`) |
| RF-04 | RF | Antenna/module keep-outs per datasheet | Detuning | A once drawn; S to derive |
| FP-01 | Footprints | Footprint matches the ordered package; symbol pinout matches | Unassemblable / wrong pins | S |
| FP-02 | Footprints | Pinout drawings read in the correct view (top vs bottom) | Mirrored pinout | J |
| FP-05 | Footprints | Mask apertures on all SMT lands and PTH pads | Unsolderable | A |
| FP-12 | Footprints | SOT-23 pinouts verified (N/P, NPN/PNP; G/S/D, B/C/E): "Common error is getting SOT-23 … pinouts flipped" | Dead circuit | S |
| ZON-01 | Zones | Zones refilled after the last edit and before CAM | Stale fills | A |
| PST-01 | Paste/mask | No untented/unfilled vias in pads (except low-power QFNs) | Solder wicking | A |
| ASM-13 | Assembly | IC/diode orientation checked in the assembler's preview; option/DNP parts not auto-matched | Common PCBA mistake | J |
| HV-01 | HV | Creepage and clearance by voltage, including between layers, per the governing safety standard (IEC 60664-1 / 62368-1 / 61010-1: pollution degree, material group, overvoltage category, insulation grade, altitude), with IPC-2221C as a functional floor only ([../rules/isolation-creepage.md](../rules/isolation-creepage.md)) | Arcing | A (`creepage`, `clearance` by class) |
| HV-02 | HV | Isolation barriers adequately sized | Safety | S |
| CAM-01 | Outputs | DRC and zone fill re-run immediately before export | Stale outputs | A |
| CAM-03 | Outputs | Uploaded files are the latest and complete ("Yes, this does happen") | Wrong build | S |
| CAM-07 | Outputs | RS-274X/X2; Excellon with embedded tool list; 1:1; consistent units and offsets; no zero-size apertures | CAM errors | A |
| FLX-03 | Flex | Each flex region meets the allowed bend radius (static vs dynamic) | Cracking | S |
| FLX-05 | Flex | No vias, holes, parts or joints in bend areas or near rigid-flex transitions | Stress | A (rule areas) |

### Most-agreed Major items

The source count measures agreement among checklist authors, not failure frequency. Same-publisher keys inflate it.

| ID | Check | # sources | Auto |
|---|---|---|---|
| DFM-04 | Copper-to-edge clearance (Sierra ≥10 mil; SparkFun 8 mil) unless edge plating/launch is noted | 7 | A (`edge_clearance`) |
| PDN-01 | Decaps as close as possible, one per power pin (Altium: under 15 mm; claude-eda <3 mm, unsourced). Critical for fast ICs | 7 | S |
| SLK-01 | No silk on pads, drills, vias or exposed copper; silk clipped by mask flagged | 7 | A (`silk_over_copper`) |
| ASM-01 | Fiducials: ≥3 global (asymmetric), both sides if double-sided, 2 local diagonal at fine pitch; 40–118 mil, ~118 mil from edge | 6 | A/S |
| ASM-02 | Pin-1/polarity marks visible after assembly | 6 | S |
| DFT-01 | Test points on power rails and critical signals | 6 | S |
| HS-05 | Stubs and layer changes minimized; via count limited | 6 | A/S (`via_count`) |
| PLC-02 | Grouped by functional block; power/analog/digital/RF separated; private parts around each IC | 6 | S |
| THM-01 | Thermal reliefs on plane connections, except heat-sinking or high-current pads | 6 | A (`zone_connection`) |
| ANA-02 | Sensitive analog separated from SMPS/noisy digital, with filters between | 5 | S |
| CAM-04 | Fab drawing/notes: dimensions, datums, drill/stackup/impedance tables, IPC class, finish | 5 | J |
| DFM-01 | Features don't push fab limits unnecessarily (SparkFun: 10 mil typical, 6 mil absolute minimum) | 5 | A (margin report) |

Major items prioritized by the semantic-critic list ([critic-stack.md](critic-stack.md)):

| ID | Check |
|---|---|
| GND-10 | HS differential traces ≥1.5×W from reference voids, except at intentionally voided SMD pads (VR RP-2), and ≥90 mil from plane edges (TI, HS diff pairs) |
| GND-03 | Return/stitching vias next to signal vias at reference changes |
| PDN-02/11/15 | Lowest mounting inductance closest (value order, "smallest closest", is CONTESTED and only behind the contested-rule selector, [../rules/decoupling-pdn.md](../rules/decoupling-pdn.md)); every GND/VCC pin and decap on its own via; BGA decap staging nF → µF → bulk (Feranec's value order, same caveat) |
| PWR-02 | Switch-node copper area minimal |
| EMC-06/07 | Filter at the exit point; ESD pads in series with the track |
| PLC-07/24 | Crystal next to its IC; no unrelated parts within 1 inch (TI: "Most EMI-related crosstalk problems center around the crystal") |
| HS-17/18 | Via stubs <15 mil or back-drilled, ~30 mil antipads; equal via counts per pair |
| THM-03 | Tombstone balance: UWARG <2× copper ratio for ≤0805; kicad-happy ratio <0.3 = high risk |
| ASM-09 | Sierra passive spacing: 0402 12 mil, 0603 21 mil, 0805 30 mil |

**Correction (VK):** DFM-05 and DFM-25 cite `microvia_aspect_ratio`/`microvia_stack_depth`. These are master (KiCad 11-dev) only, and the master keyword is `hole_aspect_ratio`. On 10.x these need custom checks.

## Recommendations for our system

- **Store the 299 items as data**, not prose: ID, category, severity, automation class, threshold, threshold source, and KiCad key or checker. Drive the critic stack from that data ([critic-stack.md](critic-stack.md)) [I].
- **Make Critical items gate state exits; weight Major items as penalties** [I].
- **Build the semantic annotation layer first** (part roles, net roles, currents, voltages, frequencies). It turns 41% of the items from judgment calls into computable checks [I].
- **Load thresholds from fab/assembler profiles** with recorded provenance [I].

## Conflicts and open questions

- Severity and automation tags are one author's assignments.
- PCB Power warns that hatched planes cause lamination microvoids (ZON-04), while jnoss recommends hatched pours.
- Official JLCPCB/PCBWay DFM checklists and NCAB's (form-gated) were not retrieved.

## Sources

- research notes: [expert_workflow_and_checklists.md § Q4–Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- corrections: [verification_kicad_and_tools.md § 1 (#14), § 2.9 DRC keys](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
- corrections (VR): [verification_rules.md § 1 (RP-2, PDN-07, "smallest closest"), § 3 (classification)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also: [checklist-full-process-dfm-stackup.md](checklist-full-process-dfm-stackup.md), [checklist-full-mechanical-placement-footprints.md](checklist-full-mechanical-placement-footprints.md), [checklist-full-power-ground-hs-rf-emc.md](checklist-full-power-ground-hs-rf-emc.md), [checklist-full-thermal-routing-assembly-test.md](checklist-full-thermal-routing-assembly-test.md), [checklist-full-silk-hv-outputs-panel-flex.md](checklist-full-silk-hv-outputs-panel-flex.md), [critic-stack.md](critic-stack.md), [respin-and-fab-hold-data.md](respin-and-fab-hold-data.md)
