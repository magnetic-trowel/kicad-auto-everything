# Layout review checklist: structure, codes, Critical and most-agreed items

Scope: index of the 299-item layout-review checklist: statistics, severity/automation codes, the 41 Critical IDs, most-agreed Major IDs, how to use the data. Not here: full rows -> the five `checklist-full-*.md` files below; source keys -> [checklist-sources.md](checklist-sources.md); critic implementation -> [critic-stack.md](critic-stack.md).
Keys: review checklist, design review, 299 items, 24 categories, Critical, Major, minor, automation class, A S J, semantic annotation layer, threshold conflicts, KiCad DRC keys, DFM, respin
Tags: [P] primary; [I] inference.

## Checklist facts
1. ~30 checklists and guides merge into **299 distinct items in 24 categories**: 41 Critical, 151 Major, 107 minor (expert-workflow note; severity and automation tags are that note's assignments, from each source's rationale [I]).
2. By automation class ~37% pure geometry/DRC, ~41% need net and part semantics, ~22% need judgment, external data or simulation. Of the 41 Critical, 80–83% are at least semi-automatable (mixed-tag counting, below).
3. Biggest enabler: a **semantic annotation layer** (part roles, net roles, currents, voltages, frequencies, datasheet thresholds); build it first: it turns 41% of items from judgment into computable checks [I].
4. Store the 299 items as data (ID, category, severity, automation class, threshold, threshold source, KiCad key or checker) and drive the critic stack from it ([critic-stack.md](critic-stack.md)) [I]. Critical items gate state exits; Major items weigh as penalties [I].
5. Thresholds conflict between sources: load them from fab/assembler profiles with provenance (datasheet > fab profile > house default) [I], never hard-coded.

## Full checklist files
| File | Items |
|---|---|
| [checklist-full-process-dfm-stackup.md](checklist-full-process-dfm-stackup.md) | 57 (PRC 18, DFM 27, STK 12) |
| [checklist-full-mechanical-placement-footprints.md](checklist-full-mechanical-placement-footprints.md) | 61 (MEC 21, PLC 27, FP 13) |
| [checklist-full-power-ground-hs-rf-emc.md](checklist-full-power-ground-hs-rf-emc.md) | 81 (PDN 15, PWR 9, GND 13, HS 24, RF 6, ANA 4, EMC 10) |
| [checklist-full-thermal-routing-assembly-test.md](checklist-full-thermal-routing-assembly-test.md) | 55 (THM 6, RTE 11, ZON 7, PST 5, ASM 13, DFT 13) |
| [checklist-full-silk-hv-outputs-panel-flex.md](checklist-full-silk-hv-outputs-panel-flex.md) | 45 (SLK 14, HV 3, CAM 13, PNL 8, FLX 7) |

## Severity and automation codes
- **Sev**: C = critical (dead or unsafe board, unmanufacturable, unassemblable → respin); M = major (SI/PI/EMC/thermal/yield/reliability risk); m = minor (debug, documentation, cosmetics).
- **Auto**: A = geometry/DRC only (KiCad check or custom-rule constraint named where applicable); S = semi-automatic (needs net classes, part roles or datasheet parameters); J = judgment, external info or simulation.
- **Sources** column: keys defined in [checklist-sources.md](checklist-sources.md).

## Structure and statistics

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

## All 41 Critical items
Full rows (check, why, KiCad 10 DRC `type` keys verified in the KiCad-tools verification note) in the linked files.
- [process-dfm-stackup](checklist-full-process-dfm-stackup.md): PRC-01 Schematic review signed off before layout; PRC-02 Board/schematic parity: no missing, extra or duplicate footprints; PRC-03 Zero unrouted connections; PRC-04 DRC 100% clean; PRC-05 Rules set from fab/assembler capability before layout; PRC-12 ERC/DRC severity overrides, exclusions and "ignore" settings…; DFM-02 Annular ring ≥ fab/IPC-class minimum; DFM-03 Hole-to-hole and hole-to-copper clearance; DFM-11 PTH ≥ lead + ~0.2 mm; DFM-21 No overlapping or co-located drills; STK-01 Stackup verified with the fab; STK-09 Every controlled-impedance net matches a net-class pattern; STK-12 Stackup drawing in fab docs.
- [mechanical-placement-footprints](checklist-full-mechanical-placement-footprints.md): MEC-01 Outline, dimensions and holes match the enclosure; MEC-04 Off-board connectors match the mating standard; MEC-08 No collisions or courtyard overlaps; MEC-15 Board thickness specified and matching; MEC-17 Board-to-board connectors spaced and located for mating; PLC-27 Power stage: IC → input cap; FP-01 Footprint matches the ordered package; FP-02 Pinout drawings read in the correct view; FP-05 Mask apertures on all SMT lands and PTH pads; FP-12 SOT-23 pinouts verified.
- [power-ground-hs-rf-emc](checklist-full-power-ground-hs-rf-emc.md): PDN-05 Every IC power/ground pin connected; PDN-06 Trace/plane widths sized for current and temperature rise; PDN-13 Width computed for every track >100 mA from IPC-2221/2152; PWR-01 Switching hot loop of minimal area; PWR-07 Connectors and regulators current-rated in the chosen package; GND-02 HS nets don't cross splits/slots/voids; HS-01 Diff pairs coupled at impedance gap; RF-04 Antenna/module keep-outs per datasheet.
- [thermal-routing-assembly-test](checklist-full-thermal-routing-assembly-test.md): ZON-01 Zones refilled after the last edit and before CAM; PST-01 No untented/unfilled vias in pads; ASM-13 IC/diode orientation checked in the assembler's preview.
- [silk-hv-outputs-panel-flex](checklist-full-silk-hv-outputs-panel-flex.md): HV-01 Creepage and clearance by voltage, including between layers, per…; HV-02 Isolation barriers adequately sized; CAM-01 DRC and zone fill re-run immediately before export; CAM-03 Uploaded files are the latest and complete; CAM-07 RS-274X/X2, Excellon with tool list, 1:1; FLX-03 Each flex region meets the allowed bend radius; FLX-05 No vias, holes, parts or joints in bend areas or near rigid-flex….

## Most-agreed Major items
Source count (in parentheses) measures agreement among checklist authors, not failure frequency; same-publisher keys inflate it. Full rows in the files above. DFM-04 (7), PDN-01 (7), SLK-01 (7), ASM-01 (6), ASM-02 (6), DFT-01 (6), HS-05 (6), PLC-02 (6), THM-01 (6), ANA-02 (5), CAM-04 (5), DFM-01 (5).

Prioritised by the semantic-critic list ([critic-stack.md](critic-stack.md)): GND-10, GND-03, PDN-02/11/15, PWR-02, EMC-06/07, PLC-07/24, HS-17/18, THM-03, ASM-09.

**Correction (VK):** DFM-05 and DFM-25 cite `microvia_aspect_ratio`/`microvia_stack_depth`: master (KiCad 11-dev) only; master keyword is `hole_aspect_ratio`. On 10.x these need custom checks.

## Open questions
- Severity and automation tags are one author's assignments; validate against escaped-error data [I].
- PCB Power: hatched planes cause lamination microvoids (ZON-04) vs jnoss recommends hatched pours.
- Official JLCPCB/PCBWay DFM checklists and NCAB's (form-gated) not retrieved.

## Sources
- [expert_workflow_and_checklists.md § Q4–Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- Corrections: [verification_kicad_and_tools.md § 1 (#14), § 2.9 DRC keys](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md); VR: [verification_rules.md § 1 (RP-2, PDN-07, "smallest closest"), § 3 (classification)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- See also [respin-and-fab-hold-data.md](respin-and-fab-hold-data.md).
