# Review checklist (full): mechanical, placement, footprints

**TL;DR**
- Mechanical fit, connector orientation and board thickness are Critical and mostly need MCAD data or judgment.
- Placement items encode the expert floorplan heuristics; most are semi-automatic once part roles exist.
- Footprint and pinout errors (wrong package, mirrored or bottom-view drawings, SOT-23 flips) are among the most common board killers.
- This file holds 61 of the 299 checklist items (MEC 21, PLC 27, FP 13). The Critical items and the most-agreed Major items are summarized in [review-checklist.md](review-checklist.md).

## Key facts

Merged from about 30 checklists by the expert-workflow note. Severity and automation tags are that note's assignments, based on each source's rationale [I]. Numeric thresholds are the cited sources' values; they are fab-specific and conflict between sources, so treat them as profile parameters. Source keys (AZ, GD, KD, AL, ...) are defined in [checklist-sources.md](checklist-sources.md).

- **Sev**: C = critical (dead or unsafe board, unmanufacturable, unassemblable → respin); M = major (SI/PI/EMC/thermal/yield/reliability risk); m = minor (debug, documentation, cosmetics).
- **Auto**: A = geometry/DRC only (KiCad check or custom-rule constraint named where applicable); S = semi-automatic (needs net classes, part roles or datasheet parameters); J = judgment, external info or simulation.

| ID | Category | What to check | Why | Sev | Auto | Sources |
|---|---|---|---|---|---|---|
| MEC-01 | Mechanical | Outline, dimensions and mounting holes match the enclosure (checked in 3D with accurate models, including mechanical parts) | Board doesn't fit | C | S (MCAD) | AZ, AL, CE, VSE |
| MEC-02 | Mechanical | Mounting holes have clearance/keepout for screw head and washer | Shorts, crushed parts | M | A (keepout) | AZ, AL, HH |
| MEC-03 | Mechanical | Mounting holes deliberately plated+grounded (with stitching) or isolated | EMC/safety | M | S | AZ, PK, HH, CD |
| MEC-04 | Mechanical | Off-board connectors match the mating standard (orientation, keying, pin 1, FPC top/bottom contact); pinout reversed if connectors face each other | Mis-mating | C | J | AZ, JN, UW, SFC |
| MEC-05 | Mechanical | Clearance for mating plug/cable and latch access; connector courtyard covers the larger mating part; mating 3D model placed | Can't plug/unplug | M | S (3D) | AZ, GD, SC, UW |
| MEC-06 | Mechanical | UI elements on the outward-facing side, logically arranged | Usability | M | J | AZ, HH |
| MEC-07 | Mechanical | Component heights within the enclosure; heatsink/fan clearance | Collisions | M | S (3D) | AZ, HH, VSE |
| MEC-08 | Mechanical | No part collisions or courtyard overlaps (3D body check, nothing under other parts) | Unassemblable | C | A (Courtyards overlap) | AZ, KG, KD, UW, SCR |
| MEC-09 | Mechanical | Perimeter keepouts (card guides, conveyor border ~3 mm, mouse bites) respected | Handling, depaneling | M | A (rule area) | AZ, GD |
| MEC-10 | Mechanical | MLCCs/stress-sensitive parts away from V-scores, tabs and mounting holes, oriented against flex; soft termination for >1210 | Cracked caps | M | S | AZ, PK, SCD |
| MEC-11 | Mechanical | Connectors mechanically anchored (THT posts/hybrid), especially RF and frequently mated | Pad lift | M | J | PK, GD |
| MEC-12 | Mechanical | Edge/right-angle connectors at the edge with correct overhang; edge fingers per spec | Fit | M | S | GD, HH |
| MEC-13 | Mechanical | Tool access: IC extraction, sockets, programming fixtures, screwdrivers, probes | Serviceability | m | S | HH, CD |
| MEC-14 | Mechanical | Connectors/mounting holes on a coarse grid; round board dimensions (SparkFun: frame on 0.1" grid starting at 0,0) | MCAD, drawings | m | A | GD, SF |
| MEC-15 | Mechanical | Board thickness (and local thickness at card-edge connectors) specified and matching connectors/enclosure | "You'd be surprised how often this is overlooked" | C | J | AL3, ALP |
| MEC-16 | Mechanical | Keep-out outline follows board shape; slots/cutouts used as barriers stop nets crossing milled areas | Cut traces | M | A | AL |
| MEC-17 | Mechanical | Board-to-board connectors spaced and located for mating (stack height, alignment) | Mating | C | S (3D) | UW |
| MEC-18 | Mechanical | UI conventions (e.g., potentiometers increase clockwise) | Usability | m | J | AL |
| MEC-19 | Mechanical | Mounting holes ≥3.3 mm by default with antipads; screw head ≥40 mil larger than hole; ≥0.5 mm copper/part clearance | Fastener fit | M | A | SC, SCR, UW |
| MEC-20 | Mechanical | House-standard connector pinouts and orientation conventions reused across boards (e.g., SparkFun I2C GND, VCC, SDA, SCL) | Interoperability | m | S | SF, JN |
| MEC-21 | Mechanical | Part-to-edge distance meets assembler/handling needs (Sierra ≥125 mil; Flux ≥5 mm near panel edges) | Depanel damage | M | A | SCR, FL, SCD |
| PLC-01 | Placement | Order: fixed parts → main ICs (CPU/memory) → other ICs → power → small passives | Fixed items constrain the rest | M | J (process) | FD, GD, JP, CE |
| PLC-02 | Placement | Grouped by functional block; power/analog/digital/RF separated; each IC's private parts gathered around it | Short routes, contained noise | M | S (sheet/role) | FXP, GD, KG, KF, SCD, BO |
| PLC-03 | Placement | Switching converters away from sensitive analog | Noise | M | S | GD, AZ |
| PLC-04 | Placement | Temperature-sensitive parts away from hot parts; small parts not next to high-dissipation parts | Lifetime, drift | M | S | HH, JN, SCR |
| PLC-05 | Placement | Interface ICs, ESD and filters next to their connectors | Short exposed path | M | S | HH, CE, SC |
| PLC-06 | Placement | Series/damping resistors at the source; terminations at the load | Termination works only at the correct end | M | S | HH, JN, AL, SC |
| PLC-07 | Placement | Crystal/oscillator next to its IC with short traces and ground guard (CE default ≤5 mm) | Jitter, EMI | M | S | HH, JN, CE, AL |
| PLC-08 | Placement | ADC anti-alias filters close to the ADC input | Pickup after the filter | M | S | GD, HH |
| PLC-09 | Placement | All components placed before routing | Inserting parts later is very hard | M | J (process) | FD, MIT, VSE |
| PLC-10 | Placement | Ratsnest length and crossings minimized; short high-speed lengths prioritized | Routability proxy | M | A | KG, KF, AL, BO |
| PLC-11 | Placement | Routability trial: quick autoroute ≥85% completion before committing | Placement and layer-count problems surface early | M | A | BO, VSE |
| PLC-12 | Placement | Routing channels between dense ICs (memories, BGAs) | Escape room | M | S | FD, BO |
| PLC-13 | Placement | Rework: any part replaceable without removing others; tweezer/iron access | Repairability | m | S | JN, GD, ICD, AL |
| PLC-14 | Placement | No routing under noisy/sensitive parts or under inductors (unless a GND plane is between); no vias under metal-film resistors | Coupling | m | S | HH, GD, UW, AL, SCR |
| PLC-15 | Placement | Polarized/like parts in one orientation or a repeatable pattern | Human/AOI inspection | m | A | GD, JN, HH, BO |
| PLC-16 | Placement | Footprints on a regular grid (Olney: 100 mil large, 25 mil chips; SparkFun 0.05"; Pikafu 5 mil origin grid) | Neatness, MCAD | m | A | GD, PK, BO, SF |
| PLC-17 | Placement | Tall parts don't shadow small parts for AOI; SMD ≥2–5 mm from THT joints if selective soldering | Inspection/soldering | m | S | GD |
| PLC-18 | Placement | Nearby inductors oriented/spaced to limit magnetic coupling | Crosstalk | m | S | CE (unsourced) |
| PLC-19 | Placement | Heat sources placed for airflow/edge; copper for spreading | Thermal | M | S | CE, JN, VSE |
| PLC-20 | Placement | Bottom-side lands aligned with top-side lands to open via space | Via channels | m | S | BO |
| PLC-21 | Placement | Parts placed by cross-probing from the schematic by function and importance | Placement reflects function | M | J (process) | BO |
| PLC-22 | Placement | Pre-placement fit check (autoplace or area estimate) that everything fits the outline | Detect impossible boards early | M | A | BO, KF |
| PLC-23 | Placement | Small chip parts not adjacent to tall or high-thermal-mass parts (UWARG ≥1 mm) | Shadowing, soldering, rework | m | A/S | AL, UW, SCR |
| PLC-24 | Placement | No unrelated components within 1 inch of a microcontroller crystal (TI EMI guideline) | "Most EMI-related crosstalk problems center around the crystal" | M | S | TI-EMI |
| PLC-25 | Placement | Circuits with similar supply/ground domains grouped together | PDN, isolation | m | S | SCD |
| PLC-26 | Placement | Pin 1 of all ICs in the same orientation where function allows; repeated parts in a clear matrix | Inspection, assembly | m | A | BO |
| PLC-27 | Placement | Power-stage order: IC → input cap (placed and routed immediately, on the IC's layer for integrated converters; vias and plane coverage are scored through the loop-inductance estimate, and vertical loops to the first inner plane are allowed, [../rules/power/hot-loops.md](../rules/power/hot-loops.md)) → inductor/catch diode → output cap → small-signal parts → single-point ground and vias | The hot loop dominates converter behavior | C | J/S | TI-BUCK, TI-1229 |
| FP-01 | Footprints | Footprint matches the ordered package (e.g., not 0805 for 0603); symbol pinout matches the package | Unassemblable / wrong pins | C | S | AZ, FL, SFC |
| FP-02 | Footprints | Pinout drawings read in the correct view (top vs bottom) | Mirrored pinout | C | J | AZ, HH, MF2 |
| FP-03 | Footprints | 1:1 printout checked against physical parts | Dimension errors | M | J | AZ, GD, JN, SFC |
| FP-04 | Footprints | 3D models present and verified | Valid MCAD checks | M | S | AZ, AL |
| FP-05 | Footprints | Mask apertures on all SMT lands and PTH pads | Unsolderable pads | C | A | AZ, PP, SC, SFC |
| FP-06 | Footprints | SMD vs NSMD pad definition (BGA) confirmed | Joint reliability | M | S | AZ, GD |
| FP-07 | Footprints | New/vendor footprints checked against the latest datasheet land pattern | Vendor libraries are often wrong | M | J | JN, HH, FL, VSE, SCD |
| FP-08 | Footprints | Courtyard present and valid; footprint matches library copy and symbol filters | Overlap checks rely on courtyards | m | A | KD |
| FP-09 | Footprints | No vias embedded in footprints | Via consolidation | m | A | PK |
| FP-10 | Footprints | Exposed/thermal pads present; assembly note if the pad is the only GND connection | Function | M | S | HH |
| FP-11 | Footprints | SMT pad length ≥ lead + ~8 mil | Fillet | M | S | JN |
| FP-12 | Footprints | SOT-23 transistor/MOSFET pinouts verified (N vs P, NPN vs PNP; G/S/D, B/C/E) | "Common error is getting SOT-23 … pinouts flipped" | C | S | MF2, SFC |
| FP-13 | Footprints | Courtyard reflects the real body where it extends beyond the pads | Pick-and-place collisions | M | S | ALP |

## Recommendations for our system

- Store these rows as machine-readable data (ID, severity, automation class, threshold, threshold source, KiCad key) and drive the critic stack from it; see [critic-stack.md](critic-stack.md).
- Load every numeric threshold from a fab/assembler profile with provenance (datasheet > fab profile > house default) [I].

## Conflicts and open questions

- Severity/automation tags are one author's assignments and need validation against escaped-error data [I].
- Thresholds conflict between sources (e.g. silk height 25 mil vs 1.0 mm vs 50 mil; edge clearance 8 vs 10 mil; part-to-edge 125 mil vs 5 mm).
- KiCad DRC key names in the Auto column follow the source note; the verified KiCad 10 key list is in [../kicad/drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md).

## Sources

- research notes: [expert_workflow_and_checklists.md § Q4 Master checklist table](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- corrections: [verification_kicad_and_tools.md § 1 Corrections table](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
- source checklists and their URLs: [checklist-sources.md](checklist-sources.md)

See also: [review-checklist.md](review-checklist.md), [critic-stack.md](critic-stack.md), [respin-and-fab-hold-data.md](respin-and-fab-hold-data.md)
