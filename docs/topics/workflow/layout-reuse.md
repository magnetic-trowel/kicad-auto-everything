# Layout reuse: hierarchy, EVM layouts, multichannel and design blocks

**TL;DR**
- The schematic's functional grouping becomes the floorplan's skeleton. Experts place by cross-probing and group each IC's private parts before arranging blocks.
- For power ICs, the lowest-risk move is to copy the datasheet or EVM layout (TI). Experts also warn that app notes are "Wrong until Proven Right" (Ritchey via Hartley), so reused layouts still need checking.
- KiCad 9.0 added multichannel Repeat Layout (isomorphism-checked) and component classes. KiCad 10.0 added PCB design blocks (saved layout fragments).
- An EVM-layout design-block library keyed by MPN and topology would automate TI's "least risk" path. Datasheet guidance should compile into constraints, not copied geometry.
- No open dataset of reference layouts and no PCB layout-retrieval paper exists.

## Key facts

Tags: [P] primary; [S] snippet/secondary; [V] vendor; [I] inference. Practitioner quotes add a qualifier: [P/E] expert, [P/C] community opinion, [P/A] single anecdote.

### KiCad reuse primitives

| Feature | Facts | Version | Source |
|---|---|---|---|
| Select by sheet; cross-selection; Pack and Move (P); Move Individually (Ctrl+M); Align/Distribute; Auto-Place | Documented recipe: select bypass caps in the schematic, then Move Individually to place each near its IC | — | [pcbnew editing docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc) [P] |
| Multichannel Repeat Layout | Channels come from repeated hierarchical sheets (recommended as "most common and convenient"), component classes or named groups. Equivalent channels need the same symbol count, prefixes, footprints and connections. "Generate Placement Rule Areas" builds a convex hull per channel, rectified to 90°. Channels are matched by topology isomorphism (refdes prefix + pin connectivity), with ties broken by sheet instance, then proximity. Routing is copied only when fully enclosed | 9.0.0 (2025-02-20) | [multichannel docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_multichannel.adoc) [P]; VK §3.4 |
| Component classes | Groups of symbols/footprints that can carry DRC rules, with query functions | 9.0.0 | [KiCad 9 release](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/) [P] |
| PCB design blocks | `.kicad_blocks` libraries. "Typically, design blocks are created first as a schematic fragment, with layout added later." "Apply Design Block Layout" needs "Place as group" and a group library link | 10.0.0 (2026-03-20) | [design blocks docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_design_blocks.adoc) [P]; [KiCad 10 release](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/) [P] |
| Action names | `pcbnew.Multichannel.generatePlacementRuleAreas`, `pcbnew.Multichannel.repeatLayout`, `…applyDesignBlockLayout`, `pcbnew.PcbDesignBlockControl.saveSelectionAsDesignBlock` | 10.0 / master | VK §3.4 [P] |

### Expert practice

- **Olney:** the engineer groups the schematic into blocks "that functionally go together", and the PCB designer should follow "a logical, sequential process … Resistors are just resistors—unless you know what they do. This is the beauty of cross-probing" [P].
- **TI:** "a best-practice option with the least risk is to simply copy the PCB layout example found on the evaluation module (EVM)" ([SLYT614](https://www.ti.com/lit/pdf/slyt614)) [P]. Datasheets carry "Layout Guidelines" sections ([TPS61178](https://ti.com/document-viewer/TPS61178/datasheet/layout-guidelines-slvsda71918)) [P].
- **Feranec:** "If you compare your schematic to the schematic of an existing and working board, there is a pretty high chance, that your board will work at the first time" [P].
- **UWARG:** "anything that has an IC, have someone review the layout of that circuit and make sure it fits with the layout recommendations in the IC's datasheet" [P].
- **Adom audit skill:** compares regulator rail sizing and PHY/MAC crossovers "to the vendor EVB" [P].

**Counter-evidence:**
- Ritchey, quoted on Hartley's slide: "Circuit Application notes produced by IC manufacturers should be assumed Wrong until Proven Right!" ([IPC deck](https://www.ipc.org/system/files/technical_resource/E14%26S03-02.pdf)) [P/E].
- Bogatin calls the Arduino Uno R3 "how NOT to design a two-layer board": "don't apply what you see in popular open-source design" ([Altium](https://resources.altium.com/p/seven-design-guidelines-to-break-bad-habits-from-using-open-source-designs)) [P/E].
- napowderly: "even when you're reusing a reference circuit, you're often manually carrying over the constraints and figuring out which layout decisions mattered" ([HN](https://news.ycombinator.com/item?id=49570348)) [P/C].

**LLM copying of references:**
- "replicate the layout from the datasheet... basically solved. More dense layouts are a stretch" ([HN](https://news.ycombinator.com/item?id=50117725)) [P/A].
- "surprising that the LLM is so bad at stealing a ready-made RP2350 design" ([HN](https://news.ycombinator.com/item?id=49699484)) [P/C].

### Reuse in other tools

| Tool | Mechanism | Tag |
|---|---|---|
| atopile | Build a sub-module as its own target, lay it out in KiCad, then use the KiCad "atopile pull group" button ([example](https://github.com/atopile/atopile/blob/main/examples/layout_reuse/layout_reuse.ato)) | [P] |
| JITX | Circuit-port forwarding: constraints written at a sub-circuit boundary apply in any parent ([docs](https://docs.jitx.com/en/latest/essentials/SI/topology.html)) | [P] |
| tscircuit | `<group>` relative positioning and packing "to minimize trace distance" | [P] |
| Altium | Components assigned to a room move with it; rooms can be generated from component classes ([docs](https://www.altium.com/documentation/altium-designer/pcb/rooms)) | [P] |
| Quilter | Detects bypass caps and switchers from schematic patterns (a cap wired to a pin, voltage-named pins, `U`/`L` refdes) ([docs](https://docs.quilter.ai/physics-constraints/bypass-capacitors)) | [V] |
| kicad-happy | Datasheets skill extracts structured JSON (pinouts, characteristics, topology) per MPN | [P] |
| PCBSchemaGen | Per-IC knowledge graph from datasheets (schematics only) ([arXiv 2602.00510](https://arxiv.org/abs/2602.00510)) | [P] |

## Recommendations for our system

- **Version-gate reuse** [I]:
  - multichannel and component classes need KiCad ≥9.0;
  - PCB design blocks need ≥10.0;
  - on 9.0, reuse means multichannel channels or copy/paste of groups.
- **Build an EVM-layout design-block library** keyed by MPN and topology, and apply a block whenever the IC appears. Run every reused block through the same critics, because experts treat app notes as unverified [I].
- **Save agent-learned blocks** to the library only after they pass their critics [I].
- **Use hierarchy as a placement prior.** Per-sheet rule areas become floorplan cells. Detect repeated sheets by isomorphism and copy them with Repeat Layout, as a placement multiplier after one channel is done [I].
- **Build a retrieval index** over a corpus keyed by (footprint/MPN, connected passives, pin functions) that supplies *relative* poses as seeds. Compile datasheet guidance (proximity, loop area, keep-away, same side) into IR constraints ([../architecture/constraint-ir.md](../architecture/constraint-ir.md)) rather than copying geometry [I].

## Conflicts and open questions

- "Copy the EVM" vs "Wrong until Proven Right": how much should reuse be trusted by default? [I]
- No open dataset of datasheet reference layouts, no PCB layout-retrieval paper and no evaluation of LLM extraction of layout guidelines were found.
- Altium snippets/device sheets and OrCAD reuse workflows were not researched. ADI AN-772 was unreachable.

## Sources

- research notes: [expert_workflow_and_checklists.md § Q3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- research notes: [constraints_verification_benchmarks.md § Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md)
- research notes: [practitioner_discussions.md § Q1d, Q3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- corrections: [verification_kicad_and_tools.md § 3.4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)

See also: [expert-state-machine.md](expert-state-machine.md), [../architecture/constraint-ir.md](../architecture/constraint-ir.md)
