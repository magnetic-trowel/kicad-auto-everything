# Deciding board size, layer count and stackup

**TL;DR**
- Board size is usually set by the enclosure. When it is free, don't over-constrain it: needed space is routinely underestimated.
- Check that parts fit before placing them: an area estimate plus a quick packer or autoplace run (Olney's only accepted use of autoplace).
- Layer count is the minimum that gives every high-speed signal a continuous reference plane, every power domain enough copper and fine-pitch parts an escape path. Add a pair of layers if channel use is above 70%, and validate with a test autoroute.
- Choose the stackup from the fab's standard stackups. If the computed impedance width is unreasonable, pick another stackup or ask the fab (craftyjon). Experts call the stackup the single most critical, most often wrong decision.
- Hi-rel mode: IPC-2221 Class 3 plus the relevant sectional standard, with test coupons on production panels (NASA).

## Key facts

Tags: [P] primary; [S] snippet/secondary; [V] vendor; [I] inference.

| Topic | Finding | Source |
|---|---|---|
| Size | "If you don't have any need to limit the size of the board, don't limit it too much. Usually the needed space and the space taken by the components+connections are underestimated" | [KiCad forum, eelik](https://forum.kicad.info/t/strategy-to-use-for-placing-components/23682) [P] |
| Fit test | Use autoplacement only "to see if all the components will fit inside the board outline before starting placement. If not, then you can re-evaluate the packaging or reduce functionality" | [Olney 2012](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design) [P] |
| Mechanics first | "Define size, shape, and mechanical features prior to starting layout"; "Start with a small layer count then increase if you need it"; every signal layer needs a GND reference; consider panelization efficiency | [Pikafu](https://github.com/Pikafu/pcb_design) [P] |
| Layer count rule | Choose "the minimum" giving "every high-speed signal … a continuous reference plane, every power domain … adequate copper, and every fine-pitch component [a clean] escape. Then add one pair of layers as margin if your routing density exceeds 70% of available channels" | [NextPCB](https://www.nextpcb.com/blog/how-many-layers-can-a-pcb-have) [P] |
| Autorouter test | "An autorouter should be nearly able to complete routing on its own if the layer count is adequate … The goal … is not to offer guidance but to evaluate the routing density — doubling as a valuable assessment of component placement" | [VSE](https://www.vse.com/blog/multilayer-pcb-stackup-planning/) [P] |
| Stackup method | "I first try to pick the layer count (based on routing complexity) and the board thickness (based on mechanical constraints)", then take a fab standard stackup and compute widths. An unreasonable width means the reference distance is wrong: pick another stackup (possibly not 1.6 mm) or ask for a custom one | [craftyjon](https://forum.kicad.info/t/about-stack-up-selection/21123) [P] |
| Criticality | Stackup is "the most critical item … what people most often get wrong"; with 2–3 signal layers per plane, "all fields intermingling in the dielectric space … that's one of the places where EMI comes from". The common 4-layer stackup with L2/L3 planes in 1.6 mm is poor | [Hartley/Altium](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley) [P] |
| Ask the fab | "always ask your manufacturer for help" (Feranec, half in jest) | [ProtoExpress](https://www.protoexpress.com/blog/sierra-pcb-layout-design-workshop-robert-feranec/) [P] |
| Interdependence | Fab parameters "cannot be evaluated independently because changing one fabrication parameter can change several layout constraints at once"; HDI/rigid-flex stackup "needs to be approved by a fabricator … before design rules can be developed" | [Altium/Peterson](https://resources.altium.com/p/pcb-design-review-checklist-gets-you-manufacturing-quickly) [P] |
| Thickness | "Board thickness (you'd be surprised how often this is overlooked)" | [Altium](https://resources.altium.com/p/how-to-navigate-the-perils-of-pcb-design-review) [P] |
| Fab tiers (2003, dated) | Conventional: 6/6 mil, 12 mil drill, 8–10 layers. Advanced: 5/5 mil, 8 mil, 15–20 layers. Leading edge: ~2/2 mil, 6 mil, 25–30 layers. "It is advisable to leave room for change and not always force the manufacturer to the limits"; write fab notes "in order of the manufacturing process" | [Robertson ch. 2](https://www.informit.com/content/images/0130674818/samplechapter/0130674818_ch02.pdf) [P] |
| 2-/4-layer rules | Watch holes and cutouts in planes; avoid buried traces in the ground plane; on 2-layer boards, power/ground trace length:width ≤3:1, run power and ground over each other | [TI SZZA009](https://www.ti.com/lit/pdf/szza009) [P] |
| Hartley stackup lists | IPC 2007 deck lists 4-, 6- and 8-layer stackups to use and "to AVOID"; "Signal Layers MUST be placed One Dielectric Layer away from Plane" | [IPC deck](https://www.ipc.org/system/files/technical_resource/E14%26S03-02.pdf) [P] |
| Hi-rel | PCBs "shall be designed in accordance with IPC-2221 (Class 3)" plus 2222/2223/2226/2228; coupons on all production panels | [GSFC-STD-8001A](https://standards.nasa.gov/system/files/tmp/GSFC-STD-8001A_Approved.pdf) [P] |
| Symmetry | Symmetric stackups prevent warpage | [PCB Power §3B](https://www.pcbpower.com/static/base/images/resources/DFM_Checklist.pdf) [P] |
| Unsourced claims | claude-eda: "2-layer with USB: can't achieve 90Ω differential impedance" (unsourced, too broad). JLCPCB "6 to 8 or more layers" and ProtoExpress "≤4 lamination cycles" were not found on the current pages | [S] |

Ritchey & Zasio *Right the First Time* Vol 2 lists the chapters "Designing the PCB Stackup", "The Four Layer PCB Problem", "Split Planes" and "How Return Currents Find Their Way from Plane to Plane", but their text was not accessible [P, ToC only].

## Recommendations for our system

- **Size**: estimate area as Σ(courtyard areas)/utilization plus edge keepouts, rounded to easy numbers. Then run a packer fit test inside the outline. On failure, enlarge the board, repackage, or flag the requirement conflict [I].
- **Layer count** is generate-and-test. Start from the minimum, run placement plus a test route, and add a layer pair if channel use is above 70% or completion is below 85–100% [I].
- **Stackup**: choose from fab catalog templates and apply craftyjon's "impedance width sanity" check. Write per-layer net-class widths [I].
- **Hi-rel mode** applies IPC Class 3 rules and coupon requirements globally [I].
- Stackup physics and EMC rules live in the rules cluster's docs; see [../rules/si-fundamentals.md](../rules/si-fundamentals.md).

## Conflicts and open questions

- No published quantitative model links board area or layer count to cost and yield; this is vendor-specific.
- Robertson's numbers are 2003-era; current fab capability must come from the fab profile.
- The KiCad 10 IPC API treats the stackup as read-only (`UpdateBoardStackup` has no handler). Stackup writes need file edits; see [../kicad/ipc-api.md](../kicad/ipc-api.md).

## Sources

- research notes: [expert_workflow_and_checklists.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- research notes: [practitioner_discussions.md § Q3 Hartley](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- corrections: [verification_kicad_and_tools.md § 1 (#2 stackup read-only)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)

See also: [expert-state-machine.md](expert-state-machine.md), [../rules/si-fundamentals.md](../rules/si-fundamentals.md)
