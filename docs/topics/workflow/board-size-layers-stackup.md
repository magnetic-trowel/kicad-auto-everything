# Deciding board size, layer count and stackup

Scope: expert practice for choosing board size, layer count and stackup (state S1–S2 of [expert-state-machine.md](expert-state-machine.md)). Not here: stackup physics and EMC rules -> [../rules/si-fundamentals.md](../rules/si-fundamentals.md).
Keys: board size, fit test, area estimate, layer count, 70% channel use, test autoroute, stackup selection, fab standard stackup, impedance width sanity, craftyjon, Hartley stackup, fab tiers, IPC-2221 Class 3, hi-rel, coupons, symmetry, warpage

Tags: [P] primary; [S] snippet/secondary; [V] vendor; [I] inference.

## Expert findings

| Topic | Finding | Source |
|---|---|---|
| Size | "If you don't have any need to limit the size of the board, don't limit it too much. Usually the needed space and the space taken by the components+connections are underestimated" (size is usually set by the enclosure) | [KiCad forum, eelik](https://forum.kicad.info/t/strategy-to-use-for-placing-components/23682) [P] |
| Fit test | Autoplace only "to see if all the components will fit inside the board outline before starting placement. If not, then you can re-evaluate the packaging or reduce functionality" | [Olney 2012](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design) [P] |
| Mechanics first | "Define size, shape, and mechanical features prior to starting layout"; "Start with a small layer count then increase if you need it"; every signal layer needs a GND reference; consider panelization efficiency | [Pikafu](https://github.com/Pikafu/pcb_design) [P] |
| Layer count rule | Choose "the minimum" giving "every high-speed signal … a continuous reference plane, every power domain … adequate copper, and every fine-pitch component [a clean] escape. Then add one pair of layers as margin if your routing density exceeds 70% of available channels" ("channel use" undefined) | [NextPCB](https://www.nextpcb.com/blog/how-many-layers-can-a-pcb-have) [P, vendor blog] |
| Autorouter test | "An autorouter should be nearly able to complete routing on its own if the layer count is adequate … The goal … is not to offer guidance but to evaluate the routing density — doubling as a valuable assessment of component placement" | [VSE](https://www.vse.com/blog/multilayer-pcb-stackup-planning/) [P] |
| Stackup method | "I first try to pick the layer count (based on routing complexity) and the board thickness (based on mechanical constraints)", then a fab standard stackup and computed widths. Unreasonable width = wrong reference distance: pick another stackup (possibly not 1.6 mm) or ask for a custom one | [craftyjon](https://forum.kicad.info/t/about-stack-up-selection/21123) [P] |
| Criticality | Stackup is "the most critical item … what people most often get wrong"; with 2–3 signal layers per plane, "all fields intermingling in the dielectric space … that's one of the places where EMI comes from". Common 4-layer stackup with L2/L3 planes in 1.6 mm is poor | [Hartley/Altium](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley) [P] |
| Ask the fab | "always ask your manufacturer for help" (Feranec, half in jest) | [ProtoExpress](https://www.protoexpress.com/blog/sierra-pcb-layout-design-workshop-robert-feranec/) [P] |
| Interdependence | Fab parameters "cannot be evaluated independently because changing one fabrication parameter can change several layout constraints at once"; HDI/rigid-flex stackup "needs to be approved by a fabricator … before design rules can be developed" | [Altium/Peterson](https://resources.altium.com/p/pcb-design-review-checklist-gets-you-manufacturing-quickly) [P] |
| Thickness | "Board thickness (you'd be surprised how often this is overlooked)" | [Altium](https://resources.altium.com/p/how-to-navigate-the-perils-of-pcb-design-review) [P] |
| Fab tiers (2003, dated) | Conventional 6/6 mil, 12 mil drill, 8–10 layers; advanced 5/5 mil, 8 mil, 15–20 layers; leading edge ~2/2 mil, 6 mil, 25–30 layers. "It is advisable to leave room for change and not always force the manufacturer to the limits"; write fab notes "in order of the manufacturing process" | [Robertson ch. 2](https://www.informit.com/content/images/0130674818/samplechapter/0130674818_ch02.pdf) [P] |
| 2-/4-layer rules | Watch holes and cutouts in planes; no buried traces in the ground plane; 2-layer power/ground trace length:width ≤3:1, run power and ground over each other | [TI SZZA009](https://www.ti.com/lit/pdf/szza009) [P] |
| Hartley stackup lists | IPC 2007 deck lists 4-, 6-, 8-layer stackups to use and "to AVOID"; "Signal Layers MUST be placed One Dielectric Layer away from Plane" | [IPC deck](https://www.ipc.org/system/files/technical_resource/E14%26S03-02.pdf) [P] |
| Hi-rel | PCBs "shall be designed in accordance with IPC-2221 (Class 3)" plus 2222/2223/2226/2228; coupons on all production panels | [GSFC-STD-8001A](https://standards.nasa.gov/system/files/tmp/GSFC-STD-8001A_Approved.pdf) [P] |
| Symmetry | Symmetric stackups prevent warpage | [PCB Power §3B](https://www.pcbpower.com/static/base/images/resources/DFM_Checklist.pdf) [P] |
| Unsourced claims | claude-eda: "2-layer with USB: can't achieve 90Ω differential impedance" (unsourced, too broad). JLCPCB "6 to 8 or more layers" and ProtoExpress "≤4 lamination cycles" not found on current pages | [S] |

Ritchey & Zasio *Right the First Time* Vol 2 chapters "Designing the PCB Stackup", "The Four Layer PCB Problem", "Split Planes", "How Return Currents Find Their Way from Plane to Plane": text not accessible [P, ToC only].

## Procedure for the agent

1. Size: area ≈ Σ(courtyard areas)/utilization + edge keepouts, rounded to easy numbers; packer fit test inside the outline; on failure enlarge, repackage or flag the requirement conflict [I].
2. Layer count (generate-and-test): start at the minimum; placement + test route; add a layer pair if channel use >70% or completion below the placement gate (Olney 85%, uncalibrated -> [expert-state-machine.md](expert-state-machine.md#state-table)) [I].
3. Stackup: fab catalog templates + craftyjon's impedance-width sanity check; write per-layer net-class widths [I].
4. Hi-rel mode: IPC Class 3 rules and coupon requirements applied globally [I].

## Open questions

- No published quantitative model links board area or layer count to cost and yield (vendor-specific).
- 70% channel-use rule: one vendor blog; no metric in the evaluation stack computes channel use yet ([../verification/evaluation-stack.md](../verification/evaluation-stack.md)).
- Robertson's numbers are 2003-era; current capability must come from the fab profile.
- KiCad 10 IPC API treats the stackup as read-only (`UpdateBoardStackup` has no handler); stackup writes need file edits -> [../kicad/ipc-api-10-vs-11.md](../kicad/ipc-api-10-vs-11.md).

## Sources

- [expert_workflow_and_checklists.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- [practitioner_discussions.md § Q3 Hartley](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- corrections: [verification_kicad_and_tools.md § 1 (#2 stackup read-only)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
