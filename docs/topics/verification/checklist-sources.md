# Review checklist: source checklists and keys

**TL;DR**
- About 30 sources were merged into the 299-item checklist: open-source checklist repos, vendor/fab checklists, team checklists, a NASA standard, TI app notes, expert columns and KiCad's DRC catalogue.
- The source keys below (AZ, GD, KD, AL, SC, PP, TI-HS, ...) are the ones used in the `Sources` column of the `checklist-full-*.md` files.
- Fab-side sources (PCB Power, Sierra, AtlasPCB) push many Critical items toward output and documentation correctness.
- Several well-known checklists are not public (NCAB form-gated, Antikernel internal "over 120" items) or were unreachable (ADI).

## Key facts

Tags: [P] = page read and checked; [S] = snippet only, wording approximate.

**Source checklists** ([P] = read in full; [S] = snippet only)
- **AZ** Andrew Zonenberg *pcb-checklist*: 72 layout and 60 schematic items. "Nearly every line item here came from the school of hard knocks" — [layout](https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md), [repo](https://github.com/azonenberg/pcb-checklist) [P]. His company Antikernel Labs runs an internal review checklist of "over 120 different potential problems" that is not public — [Antikernel PCB](https://www.antikernel.net/pcb.html) [P].
- **GD** grosdode — [pcb_checklist.md](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md) [P].
- **PK** Pikafu — [README](https://github.com/Pikafu/pcb_design) [P].
- **HH** Henrik Hansen (pcbchecklist.com) — [repo](https://github.com/henrikh/pcb-checklist) [P].
- **JN** jnoss — [repo](https://github.com/jnoss/pcb-checklist) [P].
- **KD** KiCad DRC catalogue and custom rules — [inspecting](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_inspecting.adoc), [advanced](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc) [P].
- **AL** Mark Harris, Altium "PCB Design Review Checklist" (2021-10-25) [P] — [Altium checklist](https://resources.altium.com/p/pcb-design-and-review-checklist).
  - Sections: Before Submitting; Layers; Signal Path; Components; Testing; Protection/EMI/EMC; Panels.
  - Notable items: a design rule to catch single-pin nets; bypass caps "under 15mm"; separate VCC and GND vias per decap; check traces longer than 1/6 of rise time; TVS pads in series with the track; widths calculated for tracks >100 mA (use internal-layer values without airflow); test points all on one side; panel frame, fiducials, origin mark, coupons and V-score layers.
- **ALP** Zachariah Peterson, Altium "A PCB Layout Review Checklist Gets You to Manufacturing Quickly" [P] — [Altium](https://resources.altium.com/p/pcb-design-review-checklist-gets-you-manufacturing-quickly).
  - Covers DFM points for all designs and advanced fab interdependencies.
  - HDI items: dielectric thickness, stacked vs staggered microvias, laser-via annular rings.
  - Rigid-flex table: bend radius, routing through bends, transitions, vias near flex, components out of bends, coverlay, stiffeners, flex construction, overlapping copper, impedance through flex.
  - BOM/netlist/schematic discrepancies are "one of the most common errors seen during a PCB design review".
- **AL3** Altium "perils": "many electrically or functionally incorrect design choices … will still pass design rule checks"; "board thickness (you'd be surprised how often this is overlooked)" — [Altium](https://resources.altium.com/p/how-to-navigate-the-perils-of-pcb-design-review) [P]. **AL6** "6 Areas …": requirements and traceability, version-control baselines, supply chain, DFM, compliance — [Altium](https://resources.altium.com/p/pcb-design-review-focus) [P].
- **SC** Sierra Circuits (Poulomi Ghosh), "PCB Design Checklist to Build a Flawless Board" (2022-06-22) [P] — [ProtoExpress](https://www.protoexpress.com/blog/pcb-design-checklist-to-build-flawless-board/).
  - Sections: mechanical, drill, placement, routing, mask/paste, silkscreen, fab notes, production files, BOM.
  - Sample values: mounting holes ≥3.3 mm, with screw head ≥40 mil larger than the hole; drill tolerances ±3 mil PTH and ±2 mil NPTH; mask bridge 8 mil (5 mil minimum); ≥3 fiducials.
  - This is the "Sierra Circuits layout checklist" I could not get in the first pass.
- **SCD** Sierra DFA checklist (2026-04-08) [P] — [ProtoExpress DFA](https://www.protoexpress.com/blog/pcb-design-for-assembly-checklist-important-checks-for-layout-engineers/).
  - Passive spacing table.
  - Part-to-hole ≥8 mil; part-to-annular-ring ≥7 mil.
  - Mask dam ≥4 mil; 1.6 mil mask clearance.
  - Silk ≥4 mil line and 25 mil text height.
  - Fiducials 40–118 mil, 118 mil from the edge, 3 global + 2 local.
  - Test-point distance L = 0.29·H + 0.7 mm.
  - Panel: 0.2" gaps, 118 mil from tabs.
- **SCR** Sierra "How to Perform PCB Design Review and Layout Clean-Up" (2022-10-06): separate via per ground/voltage pin; copper-to-edge ≥10 mil; via-to-via ≥6 mil; mask dam ≥5 mil; silk 25 mil/4 mil; part-to-edge ≥125 mil; production-data verification list — [ProtoExpress](https://www.protoexpress.com/blog/how-to-perform-pcb-design-review-and-layout-clean-up/) [P].
- **PP** PCB Power "PCB Design Review Checklist" PDF: sections on data package, drill, copper, mask/legend, mechanical and special layers, with "critical" items described as "the most common causes of production holds, rejections, and respins at PCB Power" — [PCB Power PDF](https://www.pcbpower.com/static/base/images/resources/DFM_Checklist.pdf) [P].
- **MF** MacroFab: "Five Tips to Clean Up Your Layout" — use the CM's DRC continuously, check silk from both sides, a test point on every node — [MacroFab](https://macrofab.com/blog/five-tips-to-clean-up-your-layout/) [P]. **MF2** pre-order checklist: SOT-23 pinouts commonly flipped, bottom-view drawings, no airwires, unique BOM designators, nothing outside the border in Gerbers — [MacroFab pre-order](https://www.macrofab.com/blog/pre-order-checklist-for-prototypes-eliminating-the-fear-of-a-bad-board) [P].
- **SF** SparkFun manufacturing rules: 10 mil traces typical, 6 mil absolute minimum; 8 mil spacing; 0603+ passives; parts on 0.005"/0.05" grid, headers on 0.1"; route from pad centers; pour isolation 12 mil; version code on bottom copper; labels on straight lines; autorouter only for prototypes — [SparkFun](https://learn.sparkfun.com/tutorials/how-to-sell-your-widget-on-sparkfun/designing-for-sparkfun-manufacture) [P]. **SFC** community checklist (colinb 2011): "Every time I make an error, I add an item to the checklist" — [SparkFun forum](https://community.sparkfun.com/t/pcb-design-tips-and-tricks/21883) [P].
- **UW** UWARG "PCB Layout Review Checklists" (v. 2026-03-08):
  - Per-IC section reviews; JLCPCB DFM via rules + clean DRC.
  - Decaps smallest→largest; copper balancing (<2× between pads for ≤0805); no traces under inductors without a GND plane between; ≥1 mm between small and tall parts; 0.5 mm mounting-hole clearance.
  - No polygon angles <45°; GND vias around high-speed vias.
  - Test points with net-name silk; a test point and an LED per rail.
  
  Source: [UWARG via Confluence REST](https://uwarg-docs.atlassian.net/wiki/spaces/EL/pages/2173501609) [P].
- **WAT** UW Rocketry review gates — [Confluence](https://uwaterloo.atlassian.net/wiki/spaces/ROCKETRY/pages/43024155641/Design+Reviews) [P]. **VSE** — [VSE](https://www.vse.com/blog/a-pcb-layout-checklist-for-error-free-manufacturing/) [P].
- **NASA** GSFC-STD-8001A (approved 2026-08-24): IPC-2221 Class 3 plus sectional standards; coupons; evaluation of non-standard features; drawing-note baseline; master drawing reviews for risk classes A/B; "A design review of the complete circuit board assembly should precede the PCB assembly process" — [GSFC-STD-8001A](https://standards.nasa.gov/system/files/tmp/GSFC-STD-8001A_Approved.pdf) [P].
- **TI-HS** SPRAAR7J "High-Speed Interface Layout Guidelines" (rev. Feb 2023): solid GND reference; not referenced to power planes; ≥1.5 W from voids; ≥90 mil from plane edge; stitching caps ≤1 µF across splits; no test points on high-speed pairs; via stubs <15 mil or back-drill; ~30 mil antipads; equal via counts; SMDs ≤0603; ESD/EMI rules — [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7) [P].
- **TI-EMI** SZZA009 — [TI](https://www.ti.com/lit/pdf/szza009) [P]. **TI-BUCK** SLYT614 — [TI](https://www.ti.com/lit/pdf/slyt614) [P]. **TI-1229** AN-1229 — [TI](https://www.ti.com/lit/pdf/snva054) [P]. **TI-FJ3** SLVAFJ3 — [TI](https://www.ti.com/lit/pdf/slvafj3) [P]. **TI** datasheet layout sections — [TPS61178](https://ti.com/document-viewer/TPS61178/datasheet/layout-guidelines-slvsda71918), [TPS55330](https://www.ti.com/document-viewer/TPS55330/datasheet/layout-guidelines-slvsbx81345) [P].
- **BO** Olney 2012 and **BOH** Olney 2024 — links above [P]. **ICD** — [PDF](https://www.icd.com.au/articles/Interactive_Place_&_Route_PCBDesign-Dec2012.pdf) [P].
- **FD** Feranec forum and workshop [P] (links above). **KF** KiCad forum [P]. **KG** KiCad Getting Started [P]. **MIT** [P].
- **FL** Flux "Common PCB Design Mistakes" (2026-04-16) — [Flux](https://www.flux.ai/p/blog/pcb-design-mistakes) [P]. **FX** Flux review process (IPC-2221C for spacing; state the IPC-6012F class) — [Flux](https://www.flux.ai/p/blog/pcb-design-review-process) [P]. **FXG** Flux grounding (splits only for audio/precision <100 kHz) — [Flux](https://www.flux.ai/p/blog/pcb-grounding-techniques) [P].
- **AP** AllPCB: prototypes "typically starting at 4-5 mils"; annular rings "must exceed 3 mils" — [AllPCB](https://www.allpcb.com/allelectrohub/the-ultimate-checklist-for-error-free-pcb-prototyping-from-schematic-to-fabrication) [P]. **BP** bestpcbs: run DFM "before quotation, before prototype release, before production release, and whenever the board changes material, layer count, package density, or assembly method" — [bestpcbs](https://www.bestpcbs.com/blog/2026/07/pcb-design-for-manufacturability-checklist/) [P].
- **AT** AtlasPCB (vendor, 2026-06-28): hold distribution and copper-balance threshold — [AtlasPCB](https://atlaspcb.com/blog/pcb-dfm-check-pre-order-verification) [P] (vendor self-report).
- **AD** Adom "kicad-board-audit" LLM skill (audit order, silenced-rule check, net-class coverage) — [Adom](https://wiki.adom.inc/adom/kicad-board-audit/files/SKILL.md) [P]. **KH** aklofas/kicad-happy (MIT; PCB analyzer methodology: decap-within-10 mm heuristic, tombstone copper ratio, layer-transition analysis, trace-proximity grid) — [methodology_pcb.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_pcb.md) [P]. **CE** claude-eda (unsourced thresholds) — [PLACEMENT-STRATEGY.md](https://github.com/l3wi/claude-eda/blob/main/templates/claude/skills/eda-pcb/reference/PLACEMENT-STRATEGY.md) [P].
- **CD** Cadence "PCB Layout Review Checklist": clearance for IC extraction tools; mounting-hole isolation; single-point analog/digital commons — [Cadence](https://resources.pcb.cadence.com/blog/2023-pcb-design-and-risk-benefit-analysis-in-component-placement) [S] (JS-rendered). **Tanner** personal JLC ordering checklist: check IC/diode orientation in the PCBA preview; keep option parts from being auto-matched; "Update this list as fails occurs" — [petertanner.dev](https://www.petertanner.dev/posts/PCB-manufacturing-checklist/) [P].
- **Other keys used in the table:**
  - **HT** Hartley — [Altium](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley), [ProtoExpress](https://www.protoexpress.com/blog/rick-hartley-pcb-design-recommendations-to-minimize-emi/) [P].
  - **NX** NextPCB — [NextPCB](https://www.nextpcb.com/blog/how-many-layers-can-a-pcb-have) [P].
  - **JR** JLCPCB routing rules — [JLCPCB](https://jlcpcb.com/blog/pcb-routing-rules-best-practices) [P].
  - **JP** JLCPCB placement guide — [JLCPCB](https://jlcpcb.com/blog/pcb-component-placement-guide-2026) [P].
  - **EN** electronics-notes — [electronics-notes](https://www.electronics-notes.com/articles/analogue_circuits/pcb-design/pcb-layout-routing.php) [P].
  - **PC** PCD&F 2019 — [PCD&F](https://www.qgdigitalpublishing.com/article/PCB+Guided+Insights/3388181/589425/article.html) [P].
  - **BG** bestpcbs ground-plane guide — [bestpcbs](https://www.bestpcbs.com/blog/2026/09/circuit-board-ground-plane-layout/) [S].
  - **FXP** Flux placement tutorial — [Flux docs](https://docs.flux.ai/tutorials/component-placement) [S] (JS-rendered).
  - **PS** ProtoExpress stack-up guide — [ProtoExpress](https://www.protoexpress.com/pcb-design-guides/pcb-stack-up-design-guide/) [S] (lamination-cycle claim not found on the current page).
- Not public or not found: NCAB's checklist is behind a form, but its section titles are visible (component packaging, placement, mechanical, routing, power design, DRC, silkscreen, Gerber review) — [NCAB](https://www.ncabgroup.com/pcb-design-checklist) [P]. Other gaps:
  - Oxide: the public RFD API lists 84 public RFDs with none on PCB review — [Oxide RFD API](https://rfd-api.shared.oxide.computer/rfd) [P].
  - Antmicro publishes an open-hardware portal and KiCad/Blender flow, not a checklist — [Antmicro](https://antmicro.com/blog/2023/04/open-hardware-portal) [P].
  - Adafruit: no checklist found [S].
  - "Ajay Bhargav": not found [S].
  - ADI: analog.com unreachable.


## Recommendations for our system

- Keep each threshold's source key next to the value in the machine-readable checklist so conflicts stay visible [I].
- Prefer fab/assembler sources (PCB Power, Sierra, the chosen CM's DRC file) for DFM thresholds and datasheets/TI notes for physics thresholds [I].

## Conflicts and open questions

- Same-publisher keys (SC/SCD/SCR; AL/ALP/AL3/AL6; MF/MF2; BO/BOH; TI-*) are counted separately in consensus counts, which inflates their items.
- Official JLCPCB/PCBWay DFM checklists, MacroFab's capabilities PDF, ADI layout notes and NCAB's checklist were not retrieved.
- claude-eda (CE) thresholds are unsourced; kicad-happy (KH) thresholds are tool heuristics, not standards.

## Sources

- research notes: [expert_workflow_and_checklists.md § Q4 Source checklists](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)

See also: [review-checklist.md](review-checklist.md), [checklist-full-process-dfm-stackup.md](checklist-full-process-dfm-stackup.md)
