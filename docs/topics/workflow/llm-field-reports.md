# LLM-driven PCB layout: practitioner field reports (2024–2026)

Scope: forum and blog quotes on where LLMs help or fail at PCB work. Not here: end-to-end case studies and tool-builder logs -> [../ux/field-reports.md](../ux/field-reports.md); failure taxonomy -> [../ux/field-failure-modes.md](../ux/field-failure-modes.md).
Keys: LLM good at review, LLM bad at routing, geometric intuition, DRC-looping, scoreboard gaming, micro-snaking, unrequested edits, parsers as eyes, orchestration, Freerouting wrapper, no validation loop

Tags: [P] primary; [V] vendor; [I] inference; [P/E] expert; [P/C] community opinion; [P/A] single anecdote; [P/T] systematic test.

## Where LLMs help

Pattern: review, datasheet cross-reference, pin-swap questions, stackup/part configuration, DRC-rule writing, net prioritization, analysis code, reading failure clusters; parsers do the analysis, the LLM narrates ([aklofas](delegation-and-expert-review.md#how-experts-review)).

| Use | Report | Source |
|---|---|---|
| Review value | "$1-2 of tokens saved me from $70-80 bugged PCBs" | [BlackRabbit1](https://news.ycombinator.com/item?id=49574053) [P/A] |
| Large schematic review | 40-page, 1200+ component schematic: found misspelled nets, wrong divider values | [nctnico](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6321348/#msg6321348) [P/A] |
| Pin errors | Found swapped IC pins before the designers; flagged open-drain pins where CMOS outputs were needed | [mawyatt](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6339972/#msg6339972), [KE5FX](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6339928/#msg6339928) [P/A] |
| Analysis code | DC IR-drop FEA on 40+ power nets and 100+ diff pairs; AC PDN impedance model validated against a DIY FRA on a DSO | [nctnico](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6344844/#msg6344844) [P/A] |
| DRC for classical routers | "better specify DRC rules in Altium so that the 'classical' algorithms are more usable"; Opus "can prioritize nets for manual vs autorouting" | [akiselev](https://news.ycombinator.com/item?id=49571739) [P/A] |
| Failure clusters → placement fix | Staggering U6–U10 → 314/314 nets on 4 layers; full case -> [../ux/field-reports.md](../ux/field-reports.md#end-to-end-case-studies) | [tinycomputers](https://tinycomputers.io/posts/what-routing-314-nets-taught-me-about-ai-assisted-pcb-design.html) [P/A] |
| Orchestration | BGA escapes → ~70 unroutable nets on 6 layers; fixed by revising fan-out; "very little token usage at the routing stage... LLM picks up the results, looks at it, tweaks, kicks off a new job" | [tonyarkles](https://news.ycombinator.com/item?id=49768092) [P/A] |
| Pin swaps, local tweaks | "excellent at 'can I swap X and Y pins on the micro?'... making adjustments to a layout for better routing in a particular area is decent" | [baby_souffle](https://news.ycombinator.com/item?id=49571799) [P/A] |
| HV/LV separation | Separated HV/LV areas, added silkscreen warnings, "way better than I did" (40 years' experience) | [leptons](https://news.ycombinator.com/item?id=50121969) [P/A] |
| Tournament routing | "run a 'tournament' style system for routing and lock in good routes"; "benchmark different kicad autoroute tools and I picked the routes I liked the best" | [sgnelson](https://news.ycombinator.com/item?id=50118893), [alex7o](https://news.ycombinator.com/item?id=49570381) [P/A] |
| Pinned traces + router | "pin a few key traces (using the kicad python api) and then use freerouting for the others" | [ckemere](https://news.ycombinator.com/item?id=50118358) [P/A] |
| Reference copying | "replicate the layout from the datasheet... basically solved. More dense layouts are a stretch... The models lack a certain... taste" | [__atx__](https://news.ycombinator.com/item?id=50117725) [P/A] |
| Parsers as eyes | "giving claude 'eyes' via python scripts so it can 'see' the empirical details... Parsers are very important"; "works much better when it is given post-processed netlists/components/circuit descriptions" | [paulca](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6222777/#msg6222777), [aklofas](https://www.reddit.com/r/KiCad/comments/1rotq1f/comment/o9j2d0d/) [P/A] |
| Datasheet extraction | Frontier models best at "pulling concrete data out of human-shaped data sources" | [JITX blog](https://blog.jitx.com/jitx-corporate-blog/testing-generative-ai-for-circuit-board-design) [V] |

## Where LLMs fail

| Failure | Report | Source |
|---|---|---|
| Geometry | "LLMs completely break down... PCB routing... their geometric intuition is nonexistent" | [akiselev](https://news.ycombinator.com/item?id=49571739) [P/A] |
| Connectors, loops, schematics | After ordering ~15 AI-designed boards: "1) Improperly rotated connectors (backwards USB port) 2) Endless routing loops for complex boards 3) Really huge/unreadable single page schematics" | [seveibar](https://news.ycombinator.com/item?id=49736506) [P/A] |
| Micro-snaking | "It will snake tiny traces through some SMD pins... instead of creating 2 45 degree turns, it does 10~30 small ones" | [rutierut](https://news.ycombinator.com/item?id=50117733) [P/A] |
| Unrequested edits | "changed the known-working parts and net routing I'd copy+pasted... changed I2C to SPI for no reason" | [the__alchemist](https://news.ycombinator.com/item?id=49740008) [P/A] |
| DRC-looping | "DRC'd it in a loop until it passed... Would a real EE vomit if they looked at it? Maybe." | [mapontosevenths](https://news.ycombinator.com/item?id=50118215) [P/A] |
| Open nets exported | "Leaving 31 nets unconnected is a weird choice?... Why export production files with unconnected nets?"; self-imposed "Power nets are routed horizontally and vertically with 90 degree bends only"; hot loop "looks massive" | [SanguineDrome](https://www.reddit.com/r/PrintedCircuitBoard/comments/1w864io/comment/p80doo9/), [SmallOne312](https://www.reddit.com/r/PrintedCircuitBoard/comments/1w864io/comment/p80aqnk/) [P/C] |
| Scoreboard gaming | 39-part SiC half-bridge, version 17, ~2 h each: "rewrote the score-board so the result looks better"; "wrote a bypass for unsolvable errors so it doesn't stand out" | [Reddit](https://www.reddit.com/r/KiCad/comments/1rdg84b/comment/o7hjiw2/) [P/A] |
| Wrong direction | "Claude develops tools for the job. So Claude has attempted to write a placer and drive Allegro's internal autorouter. That is the wrong direction" | [nctnico](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6339812/#msg6339812) [P/A] |
| Routing refusal | Opus "pretty much refused to do any routing other than power traces"; its floorplan forced via-in-pad | [tonyarkles](https://news.ycombinator.com/item?id=49742209) [P/A] |
| Melted parts, open nets | r/PCB boards where "Claude... auto router and 20 connections are left open", incl. a melted USB-C port; "it has no way to test its changes" | [rjh29](https://news.ycombinator.com/item?id=49584072) [P/C] |
| Flux | "misunderstood design intent, recommended end of life parts... placed components nonsensically and was unable to route them getting stuck in a loop of babble and repetitive moves" | [secretaliasname](https://www.reddit.com/r/PrintedCircuitBoard/comments/1u2bqnq/comment/oqyaues/) [P/A] |
| JITX GenAI test | Op-amp front end "three times the cost and size" of a TI reference, "missing many of the necessary connections"; "The context and meaning of a design … are usually absent from schematic and board design data" | [JITX](https://blog.jitx.com/jitx-corporate-blog/testing-generative-ai-for-circuit-board-design) [V] |
| Inconsistency | "getting it to ONLY use the information it got from the datasheet is not guaranteed... It's just not consistent"; overconfidence (bobc) | [Smokey](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6297314/#msg6297314) [P/A] |
| Knowledge vs experience | "knows the undergrad and grad textbooks, but has absolutely zero experience"; "can hardly put that knowledge to work" | [Scene_Cast2](https://news.ycombinator.com/item?id=49570706), [XRG](https://news.ycombinator.com/item?id=49698275) [P/C] |

## Structural explanations

1. No validation loop: "The feedback loop is too long... The model (agent) has no way to validate its work" ([sampullman](https://news.ycombinator.com/item?id=49738386)); software works because "'This is wrong, fix it' + recompile, can happen twenty times in ten minutes" ([embeng4096](https://news.ycombinator.com/item?id=47935320)) [P/C].
2. No eyes: "A schematic is a VISUAL communication medium. The LLM has no eyes and very little concept of 'spatial relationships'" ([paulca](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6216407/#msg6216407)) [P/C].
3. Training data: "hardly any professional designs are available for them to train on" (Tjalfe); "very very few examples out there as to what is wrong... need bad examples and their fixes" (Naib); an image-transformer router would need "well over 10m PCBs" ([seveibar](https://news.ycombinator.com/item?id=43513061)) [P/C].
4. Everything uses Freerouting: devbisme's seven-tool test -> [../landscape/kicad-ai-tools-and-mcp-servers.md](../landscape/kicad-ai-tools-and-mcp-servers.md#independent-hands-on-test-devbisme) [P/T]; "good-ish results telling Claude/Codex to use Freerouting... I wouldn't call that AI routing" (IAmBigFootAMA) [P/C].
5. Maturity: "EDA work is about where coding was in the pre-Opus 4.5 era" (KE5FX) [P/A]; "schematic/PCB isn't the hard part but it is the hard part for the AI" (PunchyHamster) [P/C].
6. Expert outlook (Feranec): the "most interesting technique is when AI will teach itself from combination of doing layout and running simulations... simple boards will come soon - of course quality... may be initially questionable" ([FEDEVEL](https://fedevel.com/forum/altium-designer/pcb-designer-future)) [P/E].

## Commercial tools as seen by practitioners

- Quilter (tom66, [EEVblog](https://www.eevblog.com/forum/chat/ai-pcb-layout/msg6289214/#msg6289214)) [P/A]: "Can't do HDI", "Can't do microvias", "Can't do complex breakouts from BGAs … without human intervention", "Can't do anything high density (they say generally max 20 pads per sq cm)"; ~"$1/pin"; no trial on real data without agreeing to training. Quilter docs: density above 20% "best handled manually"; envelope -> [../landscape/quilter.md](../landscape/quilter.md#architecture-and-data) [V, per VK].
- Quilter Linux board (Speedrun -> [../landscape/quilter.md](../landscape/quilter.md#project-speedrun-dec-2025)): power traces "nice fat … up to the first tight spot, and then gave up and bam 2mil tracks" ([rasz](https://news.ycombinator.com/item?id=46299786), [thomascountz](https://news.ycombinator.com/item?id=46294254)) [P/C]. Hours split -> [expert-state-machine.md](expert-state-machine.md#time-budgets).
- DeepPCB scope limits (no DDR, length matching, impedance, RF) -> [../landscape/deeppcb.md](../landscape/deeppcb.md#product) [V, per VK].
- Autocuro: "we don't consider '100% routed' to mean '100% finished'" ([HN](https://news.ycombinator.com/item?id=49709771)) [V].
- EEBench uses atopile because GUIs waste context on "coordinates, menus and application state"; it "does not yet tell us whether a model can lay out, manufacture and bring up a complete product" ([EEBench](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)) [V].

## Design implications

- LLM orchestrates, never draws copper: it infers constraints, prioritizes nets, configures DRC and routers, reads failure clusters, proposes stagger/rotate/swap/fanout fixes; engines route. Engine-free LLM routing collapses on PCBWorld -> [../routing/pcbworld.md](../routing/pcbworld.md#llm-agents) [I].
- Feed parsed, post-processed data and rendered images, not raw files [I].
- One guard per failure mode: connector orientation; no edits outside scope or to locked work; turn-count/wiggle limit; no export with open nets; agent-immutable harness -> [trust-requirements.md](trust-requirements.md) [I].
- Ship the reviewer and analyzer first [I].

## Open questions

- Hackaday's Em reports three Fable PCBs working first time ("routing can look a little wonky"); most others report failures. No controlled study exists.
- All quality claims are anecdotal; no EMC/SI lab result on an AI-placed board found.

## Sources

- [practitioner_discussions.md § Q1e, Q2b–Q2e, Q3 Feranec](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- corrections: [verification_kicad_and_tools.md § 4 Quilter, DeepPCB](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
- See also: [autorouter-distrust.md](autorouter-distrust.md), [delegation-and-expert-review.md](delegation-and-expert-review.md), [../landscape/kicad-ai-tools-and-mcp-servers.md](../landscape/kicad-ai-tools-and-mcp-servers.md)
