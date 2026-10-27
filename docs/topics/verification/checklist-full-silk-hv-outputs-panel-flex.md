# Review checklist (full): silkscreen, HV, outputs, panel, flex

**TL;DR**
- Output-package correctness (fresh fills, RS-274X/X2, latest files) is Critical and cheap to automate.
- Creepage/clearance by voltage (HV-01) is DRC-checkable once net classes carry voltages and the safety-standard inputs (pollution degree, material group, overvoltage category, insulation grade) are known.
- Flex bend-area keepouts are rule areas; bend radius needs the flex construction.
- This file holds 45 of the 299 checklist items (SLK 14, HV 3, CAM 13, PNL 8, FLX 7). The Critical items and the most-agreed Major items are summarized in [review-checklist.md](review-checklist.md).

## Key facts

Merged from about 30 checklists by the expert-workflow note. Severity and automation tags are that note's assignments, based on each source's rationale [I]. Numeric thresholds are the cited sources' values; they are fab-specific and conflict between sources, so treat them as profile parameters. Source keys (AZ, GD, KD, AL, ...) are defined in [checklist-sources.md](checklist-sources.md).

- **Sev**: C = critical (dead or unsafe board, unmanufacturable, unassemblable → respin); M = major (SI/PI/EMC/thermal/yield/reliability risk); m = minor (debug, documentation, cosmetics).
- **Auto**: A = geometry/DRC only (KiCad check or custom-rule constraint named where applicable); S = semi-automatic (needs net classes, part roles or datasheet parameters); J = judgment, external info or simulation.

| ID | Category | What to check | Why | Sev | Auto | Sources |
|---|---|---|---|---|---|---|
| SLK-01 | Silkscreen | No silk on pads, drills, vias or exposed copper; silk clipped by mask flagged; silk outside component bodies | Contaminates joints | M | A (silk_clearance; clipped by mask) | AZ, GD, JN, KD, UW, MF, SFC |
| SLK-02 | Silkscreen | Text height/thickness within fab limits (Sierra 25 mil / 4 mil; PCB Power ≥1.0 mm; UWARG 50 mil; PK ≥0.1") | Legibility | m | A (text_height, text_thickness) | AZ, KD, PK, SCD, PP, UW |
| SLK-03 | Silkscreen | Designators near their parts, unambiguous, in at most 2 orientations; no overlaps | Readability | m | A | HH, JN, GD, AL, SCD, MF |
| SLK-04 | Silkscreen | Bottom-side text mirrored | Readability | m | A (Mirrored/non-mirrored text checks) | AZ, KD, PP |
| SLK-05 | Silkscreen | Revision, date, name; blank box for serial/assembly revision; version code revised every spin | Traceability | m | S | AZ, HH, JN, GD, SF, AL, MF2 |
| SLK-06 | Silkscreen | Labels for connector pinouts/signal names, test points, LEDs, switches and states, jumpers, fuse rating, functional groups | Usability | m | S | HH, JN, AZ, SF, SC, UW |
| SLK-07 | Silkscreen | Tick marks every 5/10 pins; corner pins numbered | Probing | m | S | HH, JN |
| SLK-08 | Silkscreen | Silk removed (not crammed) in dense areas | Ambiguity | m | J | AZ |
| SLK-09 | Silkscreen | Designators annotated geographically | Finding parts | m | A | HH, JN |
| SLK-10 | Silkscreen | Connector overhang marked beyond the edge | Assembly | m | S | GD |
| SLK-11 | Silkscreen | Product markings: logos, copyright, warning/hazard labels, QA/test block with barcode | Compliance, traceability | m | J | AL, SCR |
| SLK-12 | Silkscreen | Legend clearances per fab (PCB Power: ≥8 mil to copper, ≥0.25 mm to routed edge / 0.45 mm to scored edge; Sierra: 4.5 mil silk-to-mask) | Clipping | m | A | PP, SCD |
| SLK-13 | Silkscreen | Labels aligned on straight lines; uniform text size | Visual quality | m | A | SF, SC |
| SLK-14 | Silkscreen | Silk checked from both sides | Mirroring/numbering errors | m | J | MF |
| HV-01 | HV/safety | Creepage and clearance by voltage, including between layers, per the governing safety standard (IEC 60664-1 / 62368-1 / 61010-1: pollution degree, material group, overvoltage category, insulation grade, altitude), with the IPC-2221C tables as a functional floor only ([../rules/isolation-creepage.md](../rules/isolation-creepage.md)) | Arcing | C | A (creepage, clearance by net class) | GD, HH, KD, AL, FX |
| HV-02 | HV/safety | Isolation barriers adequately sized | Safety | C | S | HH |
| HV-03 | HV/safety | Signal and power not in the same connector; connectors for different purposes not interchangeable | Mis-mating fire (Fermilab 1987) | M | J | HH |
| CAM-01 | Outputs | DRC and zone fill re-run immediately before export | Stale outputs | C | A | AZ |
| CAM-02 | Outputs | Gerber and drill exported together and inspected in an independent viewer | Misalignment | M | S/J | AZ, PK, PP, SFC |
| CAM-03 | Outputs | Uploaded files are the latest and complete (right layer count, geometry exported correctly) | "Yes, this does happen" | C | S | HH, SC |
| CAM-04 | Outputs | Fab drawing/notes: dimensions, datums, drill table, stackup table, impedance table, IPC class, finish, mask/silk colors, minimum drill and annular ring, blind/buried/via-fill notes | Fab intent | M | J | PK, FX, SC, SCR, PP |
| CAM-05 | Outputs | Assembly drawing: paste type, staking, hole sizes | Assembly intent | m | J | PK |
| CAM-06 | Outputs | Gerber X2; drill format stated | Fewer CAM errors | m | A | GD |
| CAM-07 | Outputs | RS-274X/X2 (not RS-274D); Excellon with embedded tool list; 1:1 scale; consistent units and zero offset across Gerber and drill; no zero-size apertures | CAM errors, misalignment | C | A | PP |
| CAM-08 | Outputs | Readme/fab notes listing every file, a 24-h contact, intentional opens/shorts and special requirements; no CAD/Office files in the package | Fab communication | M | J | PP, SC |
| CAM-09 | Outputs | IPC-356 netlist (or ODB++ / IPC-2581) delivered for bare-board electrical test | Netlist compare at fab | M | A | SC |
| CAM-10 | Outputs | Unwanted tool-generated layers removed; outline on a layer sent to fab; mechanical layer has dimensions, reference hole, drill map, countersink details; keep-out layer separate from outline | Fab clarity | M | S | SC, SCR, AL, PP |
| CAM-11 | Outputs | Final Gerbers from the manufacturer approved before production, especially on re-orders after changes | Wrong revision built | M | J | SC |
| CAM-12 | Outputs | No title block or features outside the board border in Gerber/ODB++; BOM designators unique | Upload errors | m | A | MF2 |
| CAM-13 | Outputs | Drawing-note baseline addresses all critical requirements; master drawing reviewed (hi-rel) | Requirement flow-down | M | J | NASA |
| PNL-01 | Panel | Panelization specified (tabs vs V-score); rails ≥3 mm; stiffness | Handling | m | S | AZ, GD |
| PNL-02 | Panel | Panel-position markers | Process debug | m | A | AZ |
| PNL-03 | Panel | Tracks/parts clear of depanel zones (Sierra: ≥118 mil from tabs; no perforated tabs next to sensitive parts) | Damage | M | A | GD, AZ, SCD |
| PNL-04 | Panel | Frame area for conveyors and clamping; panel not too large for board thickness | Handling, bounce | m | S | AL |
| PNL-05 | Panel | Panel silkscreen (QA blanks, date, machine/company, barcode, PN/rev); panel fiducials and origin mark | Traceability | m | S | AL, SCD |
| PNL-06 | Panel | Boards in the same orientation; ≥0.2" gaps; no V-score where parts overhang edges | Depanel damage | m | A | SCD |
| PNL-07 | Panel | V-score/mill/tab layers present and aligned with the board | Fab | m | A | AL |
| PNL-08 | Panel | Test coupons on production panels (hi-rel) | Structural-integrity testing | m | J | NASA, AL |
| FLX-01 | Flex | Flex components oriented to minimize bending forces | Cracking | M | S | AZ |
| FLX-02 | Flex | Teardrops on wire-to-pad connections | Cracks | M | A | AZ |
| FLX-03 | Flex | Each flex region meets the allowed bend radius (static vs dynamic) for its construction | Cracking | C | S | ALP |
| FLX-04 | Flex | Traces cross bends perpendicular and curved with no sharp corners; no overlapping copper on adjacent flex layers (I-beaming) | Strain, stiffness | M | S | ALP |
| FLX-05 | Flex | Vias, plated holes, components and solder joints kept out of bend areas and away from rigid-flex transitions | Stress | C | A (rule areas) | ALP |
| FLX-06 | Flex | Coverlay openings allow for registration/adhesive flow; stiffeners match the mechanical function | Assembly | M | S | ALP |
| FLX-07 | Flex | Impedance continuity through rigid-to-flex transitions | SI | M | J/sim | ALP |

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
