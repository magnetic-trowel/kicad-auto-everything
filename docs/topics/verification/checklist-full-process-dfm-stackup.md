# Review checklist (full): process, DFM, stackup

**TL;DR**
- Process items are mostly gates: schematic sign-off, parity, zero unrouted, DRC clean with waivers audited, rules from fab capability.
- DFM items are almost all DRC-checkable once rules mirror the fab profile; thresholds differ by fab, so load them from a profile.
- Stackup items are where fabs put orders on hold: verify with the fab and publish an unambiguous stackup and impedance table.
- STK-09 (every controlled-impedance net matches a class) is a cheap, high-value automatic check.
- This file holds 57 of the 299 checklist items (PRC 18, DFM 27, STK 12). The Critical items and the most-agreed Major items are summarized in [review-checklist.md](review-checklist.md).

## Key facts

Merged from about 30 checklists by the expert-workflow note. Severity and automation tags are that note's assignments, based on each source's rationale [I]. Numeric thresholds are the cited sources' values; they are fab-specific and conflict between sources, so treat them as profile parameters. Source keys (AZ, GD, KD, AL, ...) are defined in [checklist-sources.md](checklist-sources.md).

- **Sev**: C = critical (dead or unsafe board, unmanufacturable, unassemblable → respin); M = major (SI/PI/EMC/thermal/yield/reliability risk); m = minor (debug, documentation, cosmetics).
- **Auto**: A = geometry/DRC only (KiCad check or custom-rule constraint named where applicable); S = semi-automatic (needs net classes, part roles or datasheet parameters); J = judgment, external info or simulation.

| ID | Category | What to check | Why | Sev | Auto | Sources |
|---|---|---|---|---|---|---|
| PRC-01 | Process | Schematic review signed off before layout; pin/gate swaps made during layout back-annotated and re-reviewed | Layout of an unreviewed or out-of-sync schematic carries its errors forward | C | S (parity auto; sign-off J) | AZ, VSE, WAT |
| PRC-02 | Process | Board/schematic parity: no missing/extra/duplicate footprints, pad nets match schematic, footprint attributes match symbol ("update PCB from schematic") | LVS | C | A (DRC: Missing/Extra/Duplicate footprint; Pad net doesn't match schematic; attributes mismatch) | HH, JN, KD, AL |
| PRC-03 | Process | Zero unrouted connections / airwires; no polygon breaks | Open nets ("not unusual for a PCB to be sent to manufacturing without all the parts placed and routed") | C | A (DRC: Missing connection between items) | HH, JN, KD, VSE, MF2, AL |
| PRC-04 | Process | DRC 100% clean; every exclusion/waiver inspected and signed off | Waivers hide defects | C | A (+J for waivers) | AZ, GD, KD |
| PRC-05 | Process | Rules (track/space, drill, annular ring, mask web, silk width, edge clearance) set from fab/assembler capability before layout and kept current; use the CM's own DRC rule file | DRC is only meaningful against real fab limits; reviewers then only confirm rules + clean DRC | C | S (set) → A (check) | GD, PK, UW, MF, SF, VSE |
| PRC-06 | Process | Layout checked against functional and non-DFM requirements (connector locations, heights, creepage, test access, thermal limits, isolation zones, keepouts) | DRC passes functionally wrong designs | M | J | AL3, ALP, AL6 |
| PRC-07 | Process | Each significant IC circuit (regulators, LDOs, MCUs, transceivers, level shifters) reviewed against its datasheet/EVM layout guidance, ideally by a separate reviewer | IC-specific constraints live in datasheets | M | J (LLM extraction → S) | UW, JN, WAT, TI-BUCK, SC |
| PRC-08 | Process | Staged reviews: pre-layout, placement, critical routing, final/DFM | Each review isolates one error class while it is cheap to fix | M | J | VSE, FX |
| PRC-09 | Process | Review tied to a version-controlled, locked baseline; design decisions documented; change log per revision | Avoid reviewing or building stale data | m | J | WAT, HH, AL6 |
| PRC-10 | Process | All parts available in the chosen package; no NRND/EOL parts; alternates identified for critical parts | A late package change forces re-layout | M | S | AZ, GD, MF2, AL6, SC |
| PRC-11 | Process | BOM, netlist and schematic synchronized | "One of the most common errors seen during a PCB design review" | M | A (parity) + S (BOM) | ALP, SC |
| PRC-12 | Process | ERC/DRC severity overrides, exclusions and "ignore" settings audited before trusting a clean result | "Anything on 'ignore' makes a clean pass hollow" | C | A (read project rule severities) | AD |
| PRC-13 | Process | DRC violations grouped by root cause (one bad footprint, keepout flag or via style) before fixing | Hundreds of violations often collapse to a few causes | m | S | AD |
| PRC-14 | Process | Non-standard features (outside IPC-2220/6010 series) identified, evaluated and approved before final design | Hi-rel risk control | M | J | NASA |
| PRC-15 | Process | Each suspected issue verified against a primary source (datasheet, vendor checklist, EVB) before it is reported or fixed | Avoid false positives and wrong fixes | M | J | AD, UW |
| PRC-16 | Process | Compliance evidence (RoHS/REACH/UL) attached to parts; compliance sign-off at milestones | Compliance as a gate | m | J | AL6 |
| PRC-17 | Process | Checklist updated after every escaped error | Organizational learning loop | m | J | SFC, AZ, Tanner |
| PRC-18 | Process | Three formal review points: after schematic, after rough placement (before routing), after completion | Large layout changes are easiest before routing | M | J | WAT, VSE, BO |
| DFM-01 | DFM | Features don't push fab limits unnecessarily (SparkFun: 10 mil traces typical, 8 when needed, 6 absolute minimum; Robertson: "not always force the manufacturer to the limits") | Yield, cost | M | A (margin-to-limit report) | AZ, GD, AP, SF, BO |
| DFM-02 | DFM | Annular ring ≥ fab/IPC-class minimum (PK: 5 mil Class 2 / 7 mil Class 3 for 10 mil vias; AP: >3 mil) | Drill breakout | C | A (annular_width) | PK, AP, KD, PP, ALP |
| DFM-03 | DFM | Hole-to-hole and hole-to-copper clearances (inner and outer layers) | Breakout, shorts | C | A (hole_clearance, hole_to_hole) | KD, BP, PP, ALP |
| DFM-04 | DFM | Copper-to-edge clearance (Sierra ≥10 mil; SparkFun 8 mil) unless edge plating or edge-launch is confirmed and noted | Exposed copper, router wear | M | A (edge_clearance) | GD, AZ, KD, BP, SCR, SF, PP |
| DFM-05 | DFM | Via aspect ratio and microvia stack rules within capability | Plating reliability | M | Custom check on KiCad 10.x (`microvia_*` DRC constraints are master/KiCad 11-dev only; master keyword is `hole_aspect_ratio`, per VK) | PK, KD, ALP |
| DFM-06 | DFM | Few unique drill sizes (combine sizes within 0.05 mm) | Faster, cheaper fab | m | A | PK, PP, SCR, ALP |
| DFM-07 | DFM | Mask dams between fine-pitch pads; no mask aperture bridging different nets | Solder bridges | M | A (bridged_mask) | BP, KD, ALP |
| DFM-08 | DFM | No copper slivers or too-narrow necks (PCB Power: ≥8 mil spacing between pads in planes) | Flaking, opens | m | A (Copper sliver; connection_width) | KD, PP |
| DFM-09 | DFM | Copper balanced per layer pair; stackup and copper weights symmetric; plane layers symmetric; inner-layer venting/thieving | Warpage, delamination | m | S | BP, PP, SCR |
| DFM-10 | DFM | Outline closed and valid; internal corners millable; external corners rounded | Unmillable shapes | M | A (Board has malformed outline) | HH, KD, PK |
| DFM-11 | DFM | PTH finished hole ≥ lead + ~0.2 mm (≥10 mil); square pins sized by diagonal; plating allowance; pad ≥ hole + 10–15 mil; through-holes that get soldered are plated | Parts won't insert; weak joints | C | S (needs lead dimensions) | GD, JN, HH, AL |
| DFM-12 | DFM | Via tenting/plugging policy decided and consistent; untented vias kept away from pads | Solder theft vs test access | m | A | GD, JN, UW |
| DFM-13 | DFM | Surface finish specified (e.g., ENIG for flatness/fine pitch) and compatible with fine-pitch pads and edge contacts | Solderability, coplanarity | M | J | AZ, PK, ALP |
| DFM-14 | DFM | Board size fits standard panels efficiently | Cost | m | J | PK |
| DFM-15 | DFM | Margins chosen for production volume ("10-50 boards doesn't mean you can 1000") | Tolerance stack-up | M | J | GD |
| DFM-16 | DFM | Feature sizes compatible with copper weight (heavier copper needs larger spacing; e.g., 8 mil at 2 oz) and inner-layer etch compensation | Etch capability | M | A (per-layer rules) + S | ALP, SC, JR, PP |
| DFM-17 | DFM | Precision holes (press-fit, alignment pins) carry tighter diameter and position tolerances | Standard tolerances are insufficient | M | J | ALP |
| DFM-18 | DFM | Layer-registration margin on small pads, antipads and plane clearances | Registration errors | M | S | ALP |
| DFM-19 | DFM | Slots, cutouts and castellations defined as routed outlines with achievable radii; no slots made from chained/overlapping drills | Tooling, rejects | M | A | ALP, PP |
| DFM-20 | DFM | Via-in-pad fill/cap/planarization specified and compatible with via geometry and outer-layer features (BGA VIP noted in fab notes) | Process compatibility | M | S | ALP, SC |
| DFM-21 | DFM | No overlapping or co-located drills; PTH and NPTH in separate or clearly marked tools | Broken bits, barrel voids, process mix-ups | C | A (DRC: Drilled holes co-located / too close) | PP, KD |
| DFM-22 | DFM | NPTH free of unused copper pads; NPTH on the contour treated as part of the outline; edge PTH noted | DRC false positives, edge errors | m | A | PP |
| DFM-23 | DFM | Drill chart has a distinct symbol per size; tolerances stated (Sierra: ±3 mil PTH / ±2 mil NPTH); drill values in whole numbers | Fab interpretation | m | A | SC, SCR, PP |
| DFM-24 | DFM | Via-to-via spacing ≥ fab minimum (Sierra 6 mil); pad fully covers hole | Breakout | M | A | SCR, KD |
| DFM-25 | DFM | HDI: dielectric thickness, stacked vs staggered microvias, laser-via annular rings, separate clearances for laser vs mechanical vias | HDI reliability | M | Custom check on KiCad 10.x (microvia DRC constraints are master-only, per VK) | ALP, KD |
| DFM-26 | DFM | Mask openings and dams meet fab spec (PCB Power: opening ≥0.06 mm, dam ≥0.08 mm; Sierra DFA: dam ≥4 mil, openings 1:1, ≥1.6 mil pad-to-mask); wider for non-green masks | Bridging, mask on pads | M | A (solder_mask_expansion, bridged_mask) | PP, SCD, SCR |
| DFM-27 | DFM | Copper fill of symmetric layer pairs within ~20% (15% for double-sided reflow) — vendor threshold | Warpage | m | A | AT |
| STK-01 | Stackup | Stackup (materials, dielectric thicknesses, copper weights, finished thickness) verified with the fab | Impedance and manufacturability depend on real materials | C | J | AZ, AL, FD, HT, ALP |
| STK-02 | Stackup | Every signal layer one dielectric from a solid reference plane; continuous ground within one layer of every signal trace; no unshielded adjacent signal layers | Field containment, return path | M | S (layer roles) | HT, PK, BOH, AL, SCR |
| STK-03 | Stackup | Controlled-impedance nets, targets and reference layers listed in fab notes | Fab tunes widths | M | S | AZ, PK, SC |
| STK-04 | Stackup | Impedance calcs include solder mask (or mask removed over RF) | Mask shifts Z | M | S | AZ, PK |
| STK-05 | Stackup | Controlled-impedance traces use the computed width/gap for their layer (per-layer net-class rules) | Mismatch → reflections | M | A (once classes are defined) | PK, HH, AL, SC |
| STK-06 | Stackup | Layer count is the minimum giving continuous references, power copper and escape; +2 layers if channel use >70%; validated by test route | Cost vs SI/routability | M | J (S estimate) | NX, VSE |
| STK-07 | Stackup | Sequential lamination cycles limited | Yield, cost | m | S | PS ([S]) |
| STK-08 | Stackup | High-speed signals reference GND planes, not power planes | Return quality ("TI does not recommend high-speed signal references to power planes") | M | S | TI-HS |
| STK-09 | Stackup | Every controlled-impedance net matches a net-class pattern (nets matching none silently get Default, e.g., USB D+/D−) | Silent impedance miss | C | A (class-coverage report) | AD |
| STK-10 | Stackup | Room for impedance/test coupons; coupons per IPC-2221 on production panels for hi-rel | Fab verification | m | J | ALP, NASA, AL |
| STK-11 | Stackup | Hi-rel: design to IPC-2221 Class 3 plus the sectional standard (2222/2223/2226/2228) | Mission reliability | M | J | NASA |
| STK-12 | Stackup | Stack-up drawing (layer order, materials, thicknesses, impedance table) in the mechanical layer / fab drawing; impedance written as "Layer N: Z ±tol, referenced to Layer M" | Ambiguous stackup is the top hold cause in one vendor's data | C | J | PP, SC, AT |

## Recommendations for our system

- Store these rows as machine-readable data (ID, severity, automation class, threshold, threshold source, KiCad key) and drive the critic stack from it; see [critic-stack.md](critic-stack.md).
- Load every numeric threshold from a fab/assembler profile with provenance (datasheet > fab profile > house default) [I].

## Conflicts and open questions

- Severity/automation tags are one author's assignments and need validation against escaped-error data [I].
- Thresholds conflict between sources (e.g. silk height 25 mil vs 1.0 mm vs 50 mil; edge clearance 8 vs 10 mil; part-to-edge 125 mil vs 5 mm).
- KiCad DRC key names in the Auto column follow the source note; the verified KiCad 10 key list is in [../kicad/drc-rule-language.md](../kicad/drc-rule-language.md).

## Sources

- research notes: [expert_workflow_and_checklists.md § Q4 Master checklist table](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- corrections: [verification_kicad_and_tools.md § 1 Corrections table](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
- source checklists and their URLs: [checklist-sources.md](checklist-sources.md)

See also: [review-checklist.md](review-checklist.md), [critic-stack.md](critic-stack.md), [respin-and-fab-hold-data.md](respin-and-fab-hold-data.md)
