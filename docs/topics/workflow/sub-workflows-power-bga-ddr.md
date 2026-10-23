# Expert micro-workflows: power stage, BGA, routing priority, DDR

**TL;DR**
- Three nested micro-workflows recur in expert sources and make natural agent sub-plans: power stage (TI), BGA fanout-with-placement (Feranec), and a routing-priority ladder (TI SZZA009 / Olney).
- **Power stage**: copy the EVM layout if possible. Otherwise place *and route* the input cap first, then inductor/diode, output cap, small-signal parts and a single-point ground. Shorten loops before widening traces.
- **BGA**: do a trial placement under the CPU, clear it, fan out from the centre, then stage decaps. Feranec stages them by value (nF → µF → bulk); value order is CONTESTED, so our default is lowest mounting inductance closest ([../rules/decoupling-pdn.md](../rules/decoupling-pdn.md)).
- **Routing ladder**: power/ground and susceptible nets by hand → clocked data → the rest. Only nets switching below 50 kHz were deemed autorouter-safe (TI, 1999).
- **DDR**: don't fully route pin groups one at a time. Reserve escape channels for the whole group first (escape-and-reserve).

## Key facts

Tags: [P] primary; [S] snippet/secondary; [I] inference. Practitioner quotes add a qualifier: [P/E] expert, [P/C] community, [P/A] anecdote.

### Power stage (switching converter)

| Step | Source text | Tag |
|---|---|---|
| Least risk | "a best-practice option with the least risk is to simply copy the PCB layout example found on the evaluation module (EVM) and shown in the datasheet" ([TI SLYT614](https://www.ti.com/lit/pdf/slyt614)) | [P] |
| Order | Input cap first, "first component placed in the layout after the IC … so that nothing else can be routed in its path", then inductor → output cap → small-signal parts → single-point ground and vias (SLYT614) | [P] |
| AN-1229 | "Remaining component placements can be taken up only after the input bypass capacitor and the catch diode are firmly in place"; "'Beefing up' traces … should be a last resort. Decreasing the length of the trace should be the first step" ([TI SNVA054](https://www.ti.com/lit/pdf/snva054)) | [P] |
| SLVAFJ3 (LM5177) | 8 steps: identify critical paths → optimize hot loops → separate differential sense lines from power planes (net ties) → gate-drive and return paths → controller layout → separate AGND/PGND → thermal vias → layout example ([TI SLVAFJ3](https://www.ti.com/lit/pdf/slvafj3)) | [P] |
| Datasheet order | TI bq25886: "Layout PCB according to this specific order is essential" (quoted on the [KiCad forum](https://forum.kicad.info/t/why-product-design-industry-prefer-manual-routing-over-autoroute-for-designing-pcb-layout/23660)) | [P/C] |
| Grouping | "transistor + inductor + capacitors should be close to each other" (Feranec) | [P] |

Hot-loop physics and the checker are covered in [../rules/power/hot-loops.md](../rules/power/hot-loops.md).

### BGA / CPU + memory (Feranec)

All quotes are from the [FEDEVEL "Placement" thread](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629) [P].

- **Order**: "start with defined components and positions (board shape, mounting holes, connectors), then continue with CPU + memories, other chips, power supplies (chips, inductors, big capacitors), finish with small components."
- **Fanout with placement**: "I do fanout and placement at the same time. Initially I do simple placement under CPU (just to see how many components we have to place there), then I move everything what should be under CPU out of the board and start from middle placing VIAs and components back."
- **Decap staging**: "nF closest to the pins, XXuF a little bit further (or around BGA), XXXuF around the BGA or/and on the way from Power to BGA."
- **Spacing**: "the memories are too close to each other (you will not have space to route tracks between them)."
- **Vias first**: Phil's Lab #95 says "Place ALL vias first!" and covers power fanout, decoupling and "Vias as Testpoints" ([FEDEVEL mirror](https://home.fedevel.com/blog/bga-pcb-design-tips-phils-lab-95)) [P/E, chapter titles].

### Routing-priority ladder

| Source | Rule | Tag |
|---|---|---|
| TI SZZA009 §2.6.3 | "Power and ground routing, as well as signals that impact susceptibility, should be laid out by hand. Any signal with clocked data … should be next. Only signals with switching rates below 50 kHz can be left safely to the autorouter. Even then, every signal should be checked for EMI issues. Routing near the crystal … should be checked" ([TI](https://www.ti.com/lit/pdf/szza009)) | [P] |
| Olney 2012 | Fan out from schematic selections, with power traces 10–20 mil and each GND/VCC on its own via; route matched-length, differential and critical nets first and **lock them**; route the rest a few groups at a time | [P] |
| PCD&F 2019 | "Avoid complete routing do-overs by routing critical lines first" | [P] |
| JLCPCB | "Route power loops, high-speed signals, differential pairs, and sensitive analog paths while the board is open" | [P] |
| triffid_hunter | "I manually route everything that should be routed a certain way (high current, high speed, switchmode, sensitive analog), and leave small signals I don't care much about (eg low speed GPIO) to the autorouter" | [P/C] |
| PowerLab Claude assistant | "first power, then high-speed, then the MCU" | [P/A] |
| Bartels user (Robert_Loos) | Pre-route VCC/GND vias, decoupling and critical nets; autoroute; then check net by net | [P/C] |
| nigelwright7557 | Rough placement → "swap autoplace" for shortest nets with fixed parts set "unmovable" → autoroute → fix star grounding (audio) → pours | [P/A] |

### DDR: escape-and-reserve

- Feranec (Sierra workshop, 2018): on DDR2/3, don't fully route all connections at once. After fully routing selected pin groups, "it became impossible to connect the la[st]…". Route signal groups with the same topology, and use stitching vias when the reference changes [P] ([ProtoExpress](https://www.protoexpress.com/blog/sierra-pcb-layout-design-workshop-robert-feranec/)).
- The expert-workflow note infers that the router should reserve channels for every net in a group before finishing any. That suits negotiated-congestion or rip-up routing better than greedy sequential routing [I].
- adrian_b makes the same point about greedy completion: the remaining nets are "much more difficult... after the easy traces have already occupied the space" [P/C].

## Recommendations for our system

- Ship each micro-workflow as a named sub-plan the state machine invokes at S6/S7/S11 ([expert-state-machine.md](expert-state-machine.md)) [I].
- In the power-stage sub-plan, place and route the input loop before anything else may use that area. Gate it on a hot-loop area check [I].
- In the BGA sub-plan, alternate trial placement and fanout until escape is feasible, then place decaps lowest mounting inductance first (package, via count, via-to-pad distance) with their own vias; use value order only behind the contested-rule selector [I].
- For buses, reserve channels for the whole group before completing any member, using a congestion-negotiating router [I].
- Treat datasheet layout-order lists (bq25886-style) as ordered constraints in the intent file ([../architecture/constraint-ir.md](../architecture/constraint-ir.md)) [I].

## Conflicts and open questions

- "Copy the EVM" (TI) conflicts with "Circuit Application notes produced by IC manufacturers should be assumed Wrong until Proven Right!" (Ritchey, on Hartley's slide). See [layout-reuse.md](layout-reuse.md).
- The <50 kHz autorouter threshold is from 1999. Modern practitioners instead route by signal class (high current, high speed, switchmode, sensitive analog) [I].

## Sources

- research notes: [expert_workflow_and_checklists.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- research notes: [practitioner_discussions.md § Q2, Q4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- primary: [TI SLYT614](https://www.ti.com/lit/pdf/slyt614), [TI SNVA054](https://www.ti.com/lit/pdf/snva054), [TI SLVAFJ3](https://www.ti.com/lit/pdf/slvafj3), [TI SZZA009](https://www.ti.com/lit/pdf/szza009), [FEDEVEL placement](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629)

See also: [expert-state-machine.md](expert-state-machine.md), [../rules/power/hot-loops.md](../rules/power/hot-loops.md), [delegation-and-expert-review.md](delegation-and-expert-review.md)
