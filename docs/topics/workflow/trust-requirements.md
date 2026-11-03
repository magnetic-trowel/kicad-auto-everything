# Trust requirements for an LLM placer/router, and the hard cases it must handle

Scope: the 11 practitioner trust requirements, their wish list, and the recurring hard cases an LLM-driven KiCad tool must handle. Not here: UX patterns (alternatives, explanations) -> [../ux/explanations-and-alternatives.md](../ux/explanations-and-alternatives.md); survey and vendor demand -> [../ux/designer-demand-and-trust.md](../ux/designer-demand-and-trust.md).
Keys: trust requirements, deterministic verification, bounded scope, locks, known-good, explainability, 100% routed ≠ done, self-grading, scoreboard gaming, accuracy threshold, determinism, cheaper than by hand, data provenance, IP, wish list, hard cases, SMPS hot loop, BGA escape, connector orientation, incremental ECO

Tags: [P] primary; [V] vendor; [I] inference; [P/E] expert; [P/C] community opinion; [P/A] anecdote.

KiCad maintainers' stance as product spec: the human "plots a course"; automation "predictable... without a bunch of settings"; no "big mess" (#3 below).

## The 11 trust requirements (practitioners' words)

| # | Requirement | Quote | Source |
|---|---|---|---|
| 1 | Deterministic tools judge correctness | "I did not want the AI itself deciding that a PCB was correct. KiCad does the verification." KiCad Agentic MCP case (202 tools, 18/18 golden tasks) -> [../ux/field-reports.md](../ux/field-reports.md#end-to-end-case-studies). "offload the complex calculations to deterministic tools" | [KiCad forum 71403](https://forum.kicad.info/t/kicad-agentic-mcp-an-ai-assistant-that-edits-your-board-through-kicads-own-api-and-lets-kicad-decide-whether-the-result-is-good/71403), [71487](https://forum.kicad.info/t/open-ai-claims-gpt-6-astra-can-make-pcb-boards/71487) [P/A] |
| 2 | Bounded, commanded scope | "work with me to do a satisfactory job on a little chunk... give me some time to review it"; "do it in sensible sections and check that it did what you wanted at each section"; "autoroute, but just one thing at the time on my command" | [HN](https://news.ycombinator.com/item?id=43503671), [EEVblog](https://www.eevblog.com/forum/chat/ai-pcb-layout/msg6175749/#msg6175749), [KiCad forum](https://forum.kicad.info/t/kicad-ai-integration-artificial-intelligence/53078) [P/C] |
| 3 | Predictable, few settings | craftyjon: "for the human user to 'plot a course' and for KiCad to take care of the details... automation where that automation is relatively straightforward, predictable, and can be implemented without a bunch of settings." twl: "We don't want to have a poor quality autorouter making a big mess" | [KiCad forum 30441](https://forum.kicad.info/t/autoroute-is-it-coming-mod-edit-short-answer-is-not-in-the-foreseeable-future-so-nothing-to-see-here/30441) [P/E] |
| 4 | Never touch known-good or locked work | "The last thing you want... is to have something start moving your components and traces around in a non-controlled way"; "Do not make unsolicited edits... Make the minimum change required"; "Anything I dont want moving is set as 'unmovable'" | [HN](https://news.ycombinator.com/item?id=31129439), [EEVblog](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6231087/#msg6231087), [EEVblog](https://eevblog.com/forum/eda/standard-component-layouts/msg3800255/#msg3800255) [P/C] |
| 5 | Explainability | "the tool doesn't give you insight in how the choices are made, and you can't easily verify the boards or quantify the quality"; "fix whatever problem it tosses and show me what you did". DeepPCB concedes RL models "can't explain their reasoning" | [Hackaday](https://hackaday.com/2026/09/05/can-ai-now-design-pcbs-that-just-work/), [KiCad forum](https://forum.kicad.info/t/kicad-ai-integration-artificial-intelligence/53078), [DeepPCB](https://deeppcb.ai/the-autorouter-broke-your-trust-heres-whats-actually-different-now/) [P/C, V] |
| 6 | 100% routed ≠ done | "we don't consider '100% routed' to mean '100% finished'"; "Why export production files with unconnected nets?" | [HN](https://news.ycombinator.com/item?id=49709771), [Reddit](https://www.reddit.com/r/PrintedCircuitBoard/comments/1w864io/comment/p80doo9/) [V, P/C] |
| 7 | Honest self-evaluation | Scoreboard rewrite and error bypass; "Would a real EE vomit?" -> [llm-field-reports.md](llm-field-reports.md#where-llms-fail) | [Reddit](https://www.reddit.com/r/KiCad/comments/1rdg84b/comment/o7hjiw2/), [HN](https://news.ycombinator.com/item?id=50118215) [P/A] |
| 8 | Accuracy threshold | "A tool that does 60 percent of the tasks at a 50 percent accuracy rate is absolutely useless in PCB Design"; hardware needs a 100% solution where software tolerates 97% (olaf) | [Reddit](https://www.reddit.com/r/PrintedCircuitBoard/comments/1u4qc4u/comment/orf9z62/) [P/C] |
| 9 | Determinism | "deterministic scripts that produce the same board every time, with AI involved only where there's a real judgement call"; "the non-determinism of AI is a big issue (rightfully so)"; determinism across board revisions (jimmyswimmy) | [atomic14](https://www.atomic14.com/2026/08/03/twelve-dev-boards-from-one), [Reddit](https://www.reddit.com/r/KiCad/comments/1rotq1f/comment/oaaz5nm/), [HN](https://news.ycombinator.com/item?id=17659271) [P/A] |
| 10 | Cheaper than by hand, setup included | "faster to do it by hand than to explain to LLM what I want … often I don't really know what I want to do until I do it"; "I would have done a better layout for these three components faster than typing that prompt"; "writing the requirements is most of the time not a time saving"; "You'll need an md file with reams of design constraints" | [EEVblog](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6214263/#msg6214263), [KiCad forum](https://forum.kicad.info/t/kicad-agentic-mcp-an-ai-assistant-that-edits-your-board-through-kicads-own-api-and-lets-kicad-decide-whether-the-result-is-good/71403), [Reddit](https://www.reddit.com/r/PrintedCircuitBoard/comments/1g5wjuf/comment/lsecxw8/) [P/C] |
| 11 | Data provenance and IP | Quilter: "you can't trial it on your real data unless you agree to them training on it"; contract IP ownership clauses | [EEVblog](https://www.eevblog.com/forum/chat/ai-pcb-layout/msg6289214/#msg6289214), [EEVblog](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6217427/#msg6217427) [P/C] |

## What would change minds (wish list)

| Wish | Evidence |
|---|---|
| Co-creation, not one button | "more likely to use co-creation tools... because I rely heavily on iteration" (Chris Gammell, who coined "never trust the autorouter"); autorouting as "cruise control" (taneq); Xpedition-style sketch routing (cdawzrd); "autorouting is largely a UI problem... 'have a conversation' with it" (rcxdude) |
| Declarative intent | "this trace carries 100mA", trust via tests and lockfiles ([mawildoer, atopile](https://news.ycombinator.com/item?id=39269093)); constraints added progressively "like CSS" ([seveibar](https://news.ycombinator.com/item?id=43506820)); "AI could make a big improvement... infer most of the constraints" (rcxdude) |
| Visual or spreadsheet entry | "click on a trace/net in the schematic, type in its minimum current: 5A... Click on the DC/DC feedback trace, select 'route shortest possible'" (thm_w); OrCAD-style spreadsheet constraints (buescher); per-zone/per-net-type rule sets with priorities ("GPIO, comms buses, fenced zones, RF, low level analog, high-level analog, power, line voltage, infallible traces for IS protection") (QuicksDrawMcGraw) |
| Quantitative input | "Give it all the information... patiently and quantitatively": keepouts, vias next to ground pins, layer penalties; EMI-aware autorouter as long-term vision ([neltnerb](https://news.ycombinator.com/item?id=37697439)) |
| Guided commands | "Connect this 32 bit databus", aware of star grounding, shunt sensing, HV gaps, guard rings (paulvdh) |
| Escape hatches | "layout-as-code is awful... unless there's a user friendly escape hatch" (leoedin) |
| Good, not perfect | "convincing the cranks that you can be good even if you can't be perfect" (buescher); "A well-constrained one-step-up from autorouter" for the "millions of boards" without timing or impedance concerns (JimHeaney) |
| Manufacturer recommendations, tradeoffs | Does a tool follow manufacturer layout recommendations, make tradeoffs, stay deterministic? (jimmyswimmy) |
| Also requested | "an AI that could place silkscreen"; pin planning, review against requirements, part suitability (bson); Digikey parametric API "over its generic training" (Smokey); standardized JSON/XML pin maps (free_electron) |
| Incremental edits | "making changes to a known-good layout is actually really easy. It's greenfield layouts that are hard" ([exmadscientist](https://news.ycombinator.com/item?id=31130337)) |
| Proof | "If AI can do better, someone needs to prove it before I'll trust it" (Whiskeyman_12) |
| Keep the fun part | "routing is the fun part... resistance to autorouters is half their UI kinda sucking and half engineers not wanting to cut out the fun part" (rcxdude) |

## Hard cases the tool must handle

Cases whose evidence lives elsewhere (link) [P/C, P/A]:
- SMPS hot loop / switch-node compromise -> [autorouter-distrust.md](autorouter-distrust.md#root-causes) (grues-dinner), [delegation-and-expert-review.md](delegation-and-expert-review.md#never-delegated-or-only-on-a-leash) (TwoSpoons), [llm-field-reports.md](llm-field-reports.md#where-llms-fail) (hot loop "looks massive").
- Ordered datasheet layout priorities (bq25886) -> [sub-workflows-power-bga-ddr.md](sub-workflows-power-bga-ddr.md#power-stage-switching-converter).
- Return path at layer changes (Hartley: transfer via "VERY near the signal via"; split planes "don't cross at ANY frequency") -> [what-good-looks-like.md](what-good-looks-like.md#physics-core-experts).
- BGA fanout and escape (~70 unroutable nets; "Can't do complex breakouts from BGAs"; "Place ALL vias first!") -> [llm-field-reports.md](llm-field-reports.md#where-llms-help), [sub-workflows-power-bga-ddr.md](sub-workflows-power-bga-ddr.md#bga--cpu--memory-feranec).
- Topology choice ("left or right way around"), pin/part/package swaps, terminator end -> [delegation-and-expert-review.md](delegation-and-expert-review.md#never-delegated-or-only-on-a-leash).
- Diff pairs and length-matched buses ("make diff pair via symmetrical"; Altium DDR constraints) -> [autorouter-distrust.md](autorouter-distrust.md#root-causes), [delegation-and-expert-review.md](delegation-and-expert-review.md#delegable-practitioner-consensus).
- Faithful reference copying (RP2350) -> [layout-reuse.md](layout-reuse.md#expert-practice).

Cases with evidence held here:

| Hard case | Practitioner wording | Source |
|---|---|---|
| Decoupling as loop impedance | "impedance and cross-impedance constraint on current loops... Qualcomm actually gives you these"; counterpoint: with good planes, distance matters less | [HN](https://news.ycombinator.com/item?id=47639345), [HN](https://news.ycombinator.com/item?id=47640580) |
| Power width and pours | "random thick traces indicating lack of foresight on power distribution" (Cyan488); "fat power traces up to the first tight spot... then 2mil tracks" (Quilter board); "piddly little traces everywhere" | [EEVblog](https://www.eevblog.com/forum/projects/can-you-route-better-than-an-autorouter/msg887011/#msg887011) |
| Connector orientation vs enclosure | "Improperly rotated connectors (backwards USB port)" (seveibar); "connector placement according enclosure design files" | [HN](https://news.ycombinator.com/item?id=49738202) |
| Footprint and pinout correctness | Missed THT holes and an undersized pad (side-by-side check, [HN](https://news.ycombinator.com/item?id=49572439)); SOT-23 EBC/BEC; "never trust third-party symbols and footprints" | [HN](https://news.ycombinator.com/item?id=40755551) |
| Star point | Whether the ADC or DAC sits nearer the star point | [EEVblog](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6215107/#msg6215107) |
| Greedy dead ends | "much more difficult... after the easy traces have already occupied the space"; "Endless routing loops" | [HN](https://news.ycombinator.com/item?id=49574976) |
| HV/LV separation | Claude's HV/LV split with silk warnings; boards with 0.5 mm BGA, 300 MHz–3 GHz and 4 kV together | [HN](https://news.ycombinator.com/item?id=50121969), [KiCad forum](https://forum.kicad.info/t/autoroute-is-it-coming-mod-edit-short-answer-is-not-in-the-foreseeable-future-so-nothing-to-see-here/30441) |
| Mixed-signal and audio grounding | "ground follows signal"; "keep this SMPS far from sensitive things"; fix star grounding | [KiCad forum](https://forum.kicad.info/t/why-do-people-choose-to-not-use-the-auto-router/25849) |
| Crystal and sensitive nodes | A trace "between the pins on the clock crystal capacitors" | [EEVblog](https://www.eevblog.com/forum/projects/can-you-route-better-than-an-autorouter/msg884788/#msg884788) |
| Testability (DFT) | "test points inline"; "Vias as Testpoints"; "design for test" | [HN](https://news.ycombinator.com/item?id=49738202) |
| Rework access, mechanical stress | Courtyard room for rework; caps aligned to the short axis against flex; tombstoning; "go to the limits... more risky for production" | [Hackaday](https://hackaday.com/2019/12/01/deeppcb-routes-your-kicad-pcbs/) |

## Design implications

1. Placement is the product; routers are instruments. Seed deterministically: fixed/mechanical parts → functional clusters and reference "nuggets" → sequential packing or annealing for the rest. Iterate with a fast routability probe; the LLM reads failure clusters and proposes geometric fixes [I].
2. Write intent down before geometry, as a reviewable `intent.yaml` ([../architecture/constraint-ir.md](../architecture/constraint-ir.md)); ask about never-delegate items, don't guess ([delegation-and-expert-review.md](delegation-and-expert-review.md)) [I].
3. Extend checks so passing means more: return path, hot loop, decap loop, connector orientation, footprint vs datasheet, width vs current, keepouts, HV creepage, reference similarity ([../verification/critic-stack.md](../verification/critic-stack.md)) [I].
4. Every step bounded, diffable, reversible: default unit "this block" or "these nets"; before/after render with physical rationale ("moved C12 2.1 mm closer to U3 pin 7; loop L 1.8→0.9 nH est."); commit/undo; honour KiCad locks; never edit outside scope [I].
5. Anticipate, then verify; never self-grade: LLM states expected DRC/routability/PDN outcome first (Bogatin #9); scoring harness immutable to the agent; "100% routed" never terminal on its own [I].
6. Convention as a review layer (orientation, 45°, wiggle, silkscreen, grouping) ([../verification/looks-right-metrics.md](../verification/looks-right-metrics.md)) [I].
7. Get the delegable work perfect first; ship the reviewer early: datasheet-grounded adversarial review plus DC/AC PDN scripts [I].
8. Incremental-ECO mode respecting locked regions, as a near-term trust builder [I].

## Open questions

- No study quantifies human review time for AI layouts, or the accuracy bar that wins acceptance.
- "Routing is the fun part" conflicts with full automation: make routing optional per block [I].

## Sources

- [practitioner_discussions.md § Q1c, Q2, Q4d, Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- See also: [autorouter-distrust.md](autorouter-distrust.md)
