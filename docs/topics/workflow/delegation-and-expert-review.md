# What experts delegate, what they never delegate, and how they review

**TL;DR**
- **Never delegated**:
  - stackup;
  - floorplan, connector and mechanical placement;
  - hot loops and grounding strategy;
  - pin, part and package swaps that change the schematic;
  - topology choices ("left or right around");
  - known-good copied blocks;
  - tradeoffs between competing requirements.
- **Delegable**:
  - length-matched buses and wide regular buses;
  - fanout and stitching vias;
  - low-speed GPIO and "last mile" traces;
  - N-copy replication;
  - routability probing and analysis scripts.
- **Delegation follows predictability.** Crisp, local rules get delegated; unencoded intent with non-local tradeoffs does not.
- **Expert review techniques**:
  - a fast red-flag visual scan;
  - footprint vs datasheet side by side;
  - adversarial datasheet review;
  - a second deep pass;
  - several DRC tools, with the fab's DFM as the source of truth;
  - deterministic analysis with LLM narration.
- **An LLM tool earns trust** by doing the delegable work perfectly first and asking explicit questions about never-delegate items.

## Key facts

Tags: [P] primary; [I] inference. Practitioner quotes: [P/E] expert, [P/C] community opinion, [P/A] anecdote, [V] vendor.

### Never delegated (or only on a leash)

| Decision | Practitioner wording | Source |
|---|---|---|
| Stackup and constraints set in advance | Motherboard-class boards are "manually routed... designed in Allegro... Lots of fancy tools for planning, bundling, interactive routing per rules"; stackup is "the most critical item" | [Reddit](https://www.reddit.com/r/PrintedCircuitBoard/comments/1qyaaye/comment/o43u4tr/), [Hartley](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley) [P/C] |
| Critical nets | Routes "high current, high speed, switchmode, sensitive analog" by hand | [triffid_hunter](https://www.reddit.com/r/ElectricalEngineering/comments/175ps81/comment/k4i6gka/) [P/C] |
| Compromises | "a switching node that needs to be big to dissipate heat from a transistor, but at the same time needs to be small to prevent EMC issues. How do you tell software where the compromise is?" | [TwoSpoons, KiCad forum](https://forum.kicad.info/t/autoroute-is-it-coming-mod-edit-short-answer-is-not-in-the-foreseeable-future-so-nothing-to-see-here/30441) [P/C] |
| Topology | Autorouters are weak at "topological decisions, so the question of going left or right way around" | [Kleinstein](https://www.eevblog.com/forum/blog/eevblog-1535-deeppcb-ai-autorouting-tested!/msg4795655/#msg4795655) [P/C] |
| Schematic-level moves | "I swapped a 0402 resistor to a 0603 in order to run a trace between the pads. Pin swapping on FPGAs"; "changed chips in order to flip the ordering of the SCL/SDA pins"; autorouters "can't move components or change pins"; "The autorouter solves the problem as you have presented it, it never reflects if there is a better presentation of the problem" | [Reddit](https://www.reddit.com/r/ElectricalEngineering/comments/1ol9qfk/comment/nmi40xq/), [KiCad forum](https://forum.kicad.info/t/autoroute-is-it-coming-mod-edit-short-answer-is-not-in-the-foreseeable-future-so-nothing-to-see-here/30441), [EEVblog](https://www.eevblog.com/forum/projects/can-you-route-better-than-an-autorouter/msg932635/#msg932635) [P/C] |
| Known-good blocks | "Seeing it make substantial changes to the known-working parts (My stake-in-the-ground), I got very nervous" | [the__alchemist, HN](https://news.ycombinator.com/item?id=49742549) [P/A] |
| Mechanical integration | "connector and mounting placement, housing interferences, cable routing"; fixed positions agreed with the mechanical engineer from a STEP file; poka-yoke interfaces, connector orientation for assembly, test features | [Smokey](https://www.eevblog.com/forum/chat/ai-pcb-layout/msg6175739/#msg6175739), [PigHillJimster](https://www.reddit.com/r/PrintedCircuitBoard/comments/1gkhlds/comment/lvlesew/), [bones222222](https://www.reddit.com/r/ElectricalEngineering/comments/1ol9qfk/comment/nmjsz52/) [P/C] |
| Terminator end, star points | "which end of the track does this terminating resistor go" needs "both technical information and design intent" | [AndyC_772](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6215107/#msg6215107) [P/C] |
| Safety, EMC, reliability | Letting a router do power supplies "would cause me a safety, emc, and reliability nightmare" | [BmanGorilla](https://www.reddit.com/r/AskElectronics/comments/1gpt5n8/comment/lwwgsta/) [P/C] |
| Layout as circuit design | "Layout is still circuit design: you just don't know any of the component values" | [cushychicken, HN](https://news.ycombinator.com/item?id=39773546) [P/C] |

### Delegable (practitioner consensus)

- **Length matching**: "Doing lenght matched buses is defintely something to let some comupter do" (Kleinstein) [P/C].
- **DDR with good constraints**: "I've seen Altium's autorouter do a good job on DDR memory interfaces … It all comes down to setting up the constraints properly" ([nctnico](https://www.eevblog.com/forum/blog/eevblog-1535-deeppcb-ai-autorouting-tested!/msg4794062/#msg4794062)) [P/C].
- **Regular buses**: matthewlai autorouted about 48 traces of a 16-bit LCD/SRAM bus in a cleared area; "Routing a lot of similar traces is where autorouters shine" [P/C].
- **Fanout, stitching, low-speed nets**:
  - "automatic fanout" for the methodical parts;
  - "Stitching vias... fanning out BGA pads, routing low-speed/non-critical nets";
  - BGA breakout and length matching wanted from KiCad [P/C].
- **Last mile**: Dave Jones's "last mile" traces [P/C].
- **Replication**: "duplicating and placing 32 subcircuit copies" ([KE5FX](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6339928/#msg6339928)) [P/A].
- **Analysis**: nctnico's LLM-written DC IR drop and AC PDN scripts [P/A].

### How experts review

| Technique | Detail | Source |
|---|---|---|
| Visual red-flag scan | "randomly placed ics and decoupling, likely wrong length matching, random thick traces indicating lack of foresight on power distribution, backwards connectors, the probably unnecessary use of BGA footprints" | [Cyan488, HN](https://news.ycombinator.com/item?id=49696205) [P/C] |
| Side-by-side | "screenshot the data sheet and the board footprint and display them side by side" | [SequoiaHope, HN](https://news.ycombinator.com/item?id=49572439) [P/A] |
| Adversarial datasheet review | "Carefully review circuitry on schematic page xx, comparing connections, signals, and pin usage against the data sheets." The model "didn't go out of its way to find problems... but when I asked it to do so... the results were very helpful" | [KE5FX](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6339872/#msg6339872) [P/A] |
| Second, deeper pass | The kicad-happy first pass missed an SOT-23 EBC/BEC error that a "deep dive and verify the pinouts" prompt caught | [Reddit](https://www.reddit.com/r/KiCad/comments/1rotq1f/comment/o9iu2ex/) [P/A] |
| Self-generated schematic checks | Net-name consistency, clock distribution, power distribution, divider-computed voltages vs net names | [nctnico](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6321348/#msg6321348) [P/A] |
| Multiple DRC tools, fab DFM as truth | Run DRC "with multiple tools"; "Keep PCBWay's DFM as the source of truth"; unit-test generators. A same-LLM audit caught a DIR pull-down bug the LLM had introduced. pcb-rnd raised 121 false positives, costing 6 h | [tinycomputers](https://tinycomputers.io/posts/what-routing-314-nets-taught-me-about-ai-assisted-pcb-design.html) [P/A] |
| Deterministic analysis, LLM narration | "The parsers do the work, the LLM generates the narrative" | [aklofas](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6232445/#msg6232445) [P/A] |
| Deterministic pipelines | "deterministic scripts that produce the same board every time, with AI involved only where there's a real judgement call"; a per-module `board.yaml` hard-errors on unsafe pins; `git describe` revision on the silkscreen; "trust, but verify" | [atomic14](https://www.atomic14.com/2026/08/03/twelve-dev-boards-from-one) [P/A] |
| Fixed review order | Phil's Lab #85: stackup → regulator → rules/vias/power → outline → decoupling → transfer vias → diff pairs → pours → silkscreen | [FEDEVEL mirror](https://home.fedevel.com/blog/fpga-pcb-design-review-phils-lab-85) [P/E] |
| Per-net highlight | Find nets "longer than the Manhattan length or spiral around the board three times" | [Olney](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design) [P] |
| Readable inputs | "At least make the schematic readable, then probably it will be possible to review it" | [ub0baa](https://www.reddit.com/r/PrintedCircuitBoard/comments/1wz5mjm/comment/pe8syq6/) [P/C] |
| Anticipate results | Bogatin #9: "Never perform a measurement or simulation without first anticipating the results" | [SI Journal](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers) [P/E] |
| Change log with visuals | Keep a "project web page with a chronological list of big changes and detailed visualizations" | [SequoiaHope](https://news.ycombinator.com/item?id=49572155) [P/A] |

## Recommendations for our system

- **Never-delegate items become explicit questions** to the user, with proposed defaults and evidence. The tool does not guess them [I].
- **Automate the delegable list first and to a high standard**: diff pairs, length-matched buses, fanout, stitching, low-speed GPIO, N-copy replication [I].
- **Ship a reviewer script in Phil's order.** Include side-by-side artifacts (footprint vs datasheet image, placement vs reference layout, before/after diff), an adversarial second pass, and a deep pinout pass [I].
- **Route every LLM claim through a deterministic check** (parsers, DRC, PDN scripts) before reporting it [I].
- **Treat pin, part and package swaps as first-class layout moves** that write back to the schematic for human approval [I].

## Conflicts and open questions

- No source measures review time for AI-generated vs human layouts.
- Phil's Lab is represented only by chapter titles; his specific placement heuristics are unread.

## Sources

- research notes: [practitioner_discussions.md § Q4b–Q4d, Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- research notes: [expert_workflow_and_checklists.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)

See also: [what-good-looks-like.md](what-good-looks-like.md), [trust-requirements.md](trust-requirements.md), [../verification/critic-stack.md](../verification/critic-stack.md)
