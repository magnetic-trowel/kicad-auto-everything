# Expert micro-workflows: power stage, BGA, routing priority, DDR

Scope: nested expert micro-workflows used as agent sub-plans at states S6/S7/S11 of [expert-state-machine.md](expert-state-machine.md). Not here: hot-loop physics and checker -> [../rules/power/hot-loops.md](../rules/power/hot-loops.md); decap ordering rule -> [../rules/decoupling-pdn.md](../rules/decoupling-pdn.md).
Keys: power stage, switching converter layout, input cap first, EVM copy, SLYT614, SNVA054 AN-1229, SLVAFJ3 LM5177, bq25886 layout order, BGA fanout with placement, Feranec, decap staging, Place ALL vias first, routing-priority ladder, SZZA009 50 kHz, escape-and-reserve, DDR

Tags: [P] primary; [S] snippet/secondary; [I] inference; [P/E] expert; [P/C] community; [P/A] anecdote.

## Power stage (switching converter)

| Step | Source text | Tag |
|---|---|---|
| Least risk | Copy the EVM/datasheet layout (TI SLYT614); conflict with "Wrong until Proven Right" -> [layout-reuse.md](layout-reuse.md#expert-practice) | [P] |
| Order | Input cap first, "first component placed in the layout after the IC … so that nothing else can be routed in its path", then inductor → output cap → small-signal parts → single-point ground and vias (SLYT614) | [P] |
| AN-1229 | "Remaining component placements can be taken up only after the input bypass capacitor and the catch diode are firmly in place"; "'Beefing up' traces … should be a last resort. Decreasing the length of the trace should be the first step" ([TI SNVA054](https://www.ti.com/lit/pdf/snva054)) | [P] |
| SLVAFJ3 (LM5177) | 8 steps: identify critical paths → optimize hot loops → separate differential sense lines from power planes (net ties) → gate-drive and return paths → controller layout → separate AGND/PGND → thermal vias → layout example ([TI SLVAFJ3](https://www.ti.com/lit/pdf/slvafj3)) | [P] |
| Datasheet order | TI bq25886: "Layout PCB according to this specific order is essential" (quoted on the [KiCad forum](https://forum.kicad.info/t/why-product-design-industry-prefer-manual-routing-over-autoroute-for-designing-pcb-layout/23660)) | [P/C] |
| Grouping | "transistor + inductor + capacitors should be close to each other" (Feranec) | [P] |

Sub-plan [I]: place and route the input loop before anything else may use that area; gate on a hot-loop area check. Treat datasheet layout-order lists (bq25886-style) as ordered constraints in the intent file ([../architecture/constraint-ir.md](../architecture/constraint-ir.md)).

## BGA / CPU + memory (Feranec)

Quotes from the [FEDEVEL "Placement" thread](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629) [P].

1. Order: "start with defined components and positions (board shape, mounting holes, connectors), then continue with CPU + memories, other chips, power supplies (chips, inductors, big capacitors), finish with small components."
2. Fanout with placement: "I do fanout and placement at the same time. Initially I do simple placement under CPU (just to see how many components we have to place there), then I move everything what should be under CPU out of the board and start from middle placing VIAs and components back."
3. Decap staging: "nF closest to the pins, XXuF a little bit further (or around BGA), XXXuF around the BGA or/and on the way from Power to BGA." Value order is CONTESTED; our default is lowest mounting inductance closest ([../rules/decoupling-pdn.md](../rules/decoupling-pdn.md)).
4. Spacing: "the memories are too close to each other (you will not have space to route tracks between them)."
5. Vias first: Phil's Lab #95 "Place ALL vias first!", power fanout, decoupling, "Vias as Testpoints" ([FEDEVEL mirror](https://home.fedevel.com/blog/bga-pcb-design-tips-phils-lab-95)) [P/E, chapter titles].

Sub-plan [I]: alternate trial placement and fanout until escape is feasible; then place decaps lowest mounting inductance first (package, via count, via-to-pad distance), each with own vias; value order only behind the contested-rule selector.

## Routing-priority ladder

Ladder: power/ground and susceptible nets by hand → clocked data → the rest.

| Source | Rule | Tag |
|---|---|---|
| TI SZZA009 §2.6.3 (1999) | "Power and ground routing, as well as signals that impact susceptibility, should be laid out by hand. Any signal with clocked data … should be next. Only signals with switching rates below 50 kHz can be left safely to the autorouter. Even then, every signal should be checked for EMI issues. Routing near the crystal … should be checked" ([TI](https://www.ti.com/lit/pdf/szza009)) | [P] |
| Olney 2012 | Fan out from schematic selections, power traces 10–20 mil, each GND/VCC on its own via; route matched-length, differential and critical nets first and **lock them**; route the rest a few groups at a time | [P] |
| PCD&F 2019 | "Avoid complete routing do-overs by routing critical lines first" | [P] |
| JLCPCB | "Route power loops, high-speed signals, differential pairs, and sensitive analog paths while the board is open" | [P] |
| triffid_hunter | Manual: high current, high speed, switchmode, sensitive analog; autorouter: low-speed GPIO -> [delegation-and-expert-review.md](delegation-and-expert-review.md#never-delegated-or-only-on-a-leash) | [P/C] |
| PowerLab Claude assistant | "first power, then high-speed, then the MCU" | [P/A] |
| Bartels user (Robert_Loos) | Pre-route VCC/GND vias, decoupling and critical nets; autoroute; check net by net | [P/C] |
| nigelwright7557 | Autoplace-with-locks flow -> [expert-state-machine.md](expert-state-machine.md#practitioner-placement-procedures-s3s8-in-practice) | [P/A] |

The <50 kHz threshold is from 1999; modern practitioners route by signal class (high current, high speed, switchmode, sensitive analog) instead [I].

## DDR: escape-and-reserve

- Feranec (Sierra workshop, 2018): on DDR2/3, don't fully route all connections at once; after fully routing selected pin groups "it became impossible to connect the la[st]…". Route signal groups with the same topology; stitching vias where the reference changes ([ProtoExpress](https://www.protoexpress.com/blog/sierra-pcb-layout-design-workshop-robert-feranec/)) [P].
- Inference (expert-workflow note): reserve channels for every net in a group before finishing any; suits negotiated-congestion or rip-up routing, not greedy sequential [I].
- adrian_b on greedy completion: remaining nets "much more difficult... after the easy traces have already occupied the space" [P/C].

## Sources

- [expert_workflow_and_checklists.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- [practitioner_discussions.md § Q2, Q4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- primary: [TI SLYT614](https://www.ti.com/lit/pdf/slyt614), [TI SNVA054](https://www.ti.com/lit/pdf/snva054), [TI SLVAFJ3](https://www.ti.com/lit/pdf/slvafj3), [TI SZZA009](https://www.ti.com/lit/pdf/szza009), [FEDEVEL placement](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629)
