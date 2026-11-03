# Why practitioners distrust autorouters (and where they use them anyway)

Scope: practitioner (forum) root causes of autorouter distrust, chip-P&R contrast, probe vs producer use, real-board comparisons. Not here: vendor/expert history of autorouter rejection and measurable checks -> [../routing/autorouter-skepticism.md](../routing/autorouter-skepticism.md); LLM field reports -> [llm-field-reports.md](llm-field-reports.md).
Keys: autorouter distrust, wrong objective, 100% routed ≠ works, placement dominates, setup catch-22, chip P&R rule decks 99.99%, routability probe, probe vs producer, via count as signal, last 20%, DeepPCB vs Freerouting vs human, CadMust-Neo

Tags: [P] primary; [I] inference; [P/E] expert; [P/C] community opinion; [P/A] anecdote; [P/T] systematic test. Each HN comment cited by its item URL.

Summary [I]: (1) "100% routed and DRC-clean" ≠ works; real objectives (return paths, loop area, current, EMC, testability, rework) live mostly outside the netlist. (2) Routing cannot fix placement; practitioners want an autoplacer more than an autorouter. (3) Encoding enough constraints costs about as much as hand routing. (4) Chip P&R is trusted because its rule decks predict function; PCB DRC does not. (5) Professionals use routers as probes of placement, and as producers only for buses, fanout and low-speed nets after critical nets.

## Root causes

| Cause | Quote | Source |
|---|---|---|
| Wrong objective | "Autorouters meet all physical rules, while violating all electrical rules" | [madengr](https://news.ycombinator.com/item?id=16358399) [P/C] |
| Wrong objective | "There are a million ways to make a PCB pass DRC and still be a completely non-functional device … put cap near pin, test points inline, make diff pair via symmetrical, keep this SMPS far from sensitive things, and make the inductor loop as tiny as you can" | [grues-dinner](https://news.ycombinator.com/item?id=43502864) [P/C] |
| Wrong objective | "many electrically or functionally incorrect design choices … will still pass design rule checks" | [Altium](https://resources.altium.com/p/how-to-navigate-the-perils-of-pcb-design-review) [P] |
| Missing information | "switching regulator has very precise layout requirements, but that status LED can be at the end of a long trace. That information simply isn't captured" | [leoedin](https://news.ycombinator.com/item?id=21663025) [P/C] |
| Missing information | PCB routing is "NP-incomplete... program doesn't have all the information" | [jmole](https://news.ycombinator.com/item?id=32402122) [P/C] |
| Missing information | Expert systems were "a disaster. The root cause of which is most of the intent is not captured in any file" | [TechnicalWhore](https://www.reddit.com/r/PrintedCircuitBoard/comments/1kwdskw/comment/mugknck/) [P/C] |
| Placement dominates | "Routing follows placement and routing can't fix placement problems"; "Good PCB design is nearly 100% about placement"; "IMO placement is one of the hard parts of board design. Routing traces is just work" | [HN](https://news.ycombinator.com/item?id=21661576), [HN](https://news.ycombinator.com/item?id=31129439), [nctnico](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6339896/#msg6339896) [P/C] |
| Setup catch-22 | "defining the constraints for an autorouter is generally more work than just manually routing" | [dlcarrier](https://news.ycombinator.com/item?id=46306575) [P/C] |
| Setup catch-22 | "the time cost of setting up the rules and net classes … is usually greater then just routing the damn board by hand... I have 1,200 component boards in commercial production that I have manually routed... Autorouter for a complete board is a beginner trap" | [dmills_00](https://www.reddit.com/r/PrintedCircuitBoard/comments/1qyaaye/comment/o42827v/) [P/C] |
| Setup catch-22 | "ONLY time I have seen an auto router do good work": 20+ layer boards with "15 EEs, 5 of whom worked almost exclusively on configuring the autorouter" | [akiselev](https://news.ycombinator.com/item?id=12061702) [P/C] |
| Wrong done-criterion | Autorouters "written by CS people... 'all tracks routed? Great. I'm done.'", "no ground plane", boards "pure hell to test and certify" | [cushychicken](https://news.ycombinator.com/item?id=43510078) [P/C] |
| Missing features | No net prioritization, poor diff pairs and buses, no best practices, no arbitrary area rules ("power trace under IMU"), Freerouting "greedily routing" | [bArray](https://news.ycombinator.com/item?id=43506335) [P/C] |
| Rip-up | A good router must "tear up stuff it already routed" | [Animats](https://news.ycombinator.com/item?id=43500803) [P/C] |
| Behaviour | "It will go to the limits imposed to it... It can't move components or change pins... [ignores] the type of signal" | [Twistx77](https://www.eevblog.com/forum/projects/can-you-route-better-than-an-autorouter/msg932635/#msg932635) [P/C] |
| Named failures | Power nets first; tombstoning from asymmetric copper; missing return vias; parallel connector pins where "the netlist doesn't capture the important bit" | HN: [omgtehlion](https://news.ycombinator.com/item?id=16357549), [petsfed](https://news.ycombinator.com/item?id=37696859), [dragontamer](https://news.ycombinator.com/item?id=37695659), [tlb](https://news.ycombinator.com/item?id=43036359) [P/C] |
| Via count as signal | "if it thinks the best it can do is 20 vias on this group of traces I don't stand a chance": router via count reveals placement problems | [tonyarkles](https://news.ycombinator.com/item?id=37700145) [P/C] |
| Smell | Reviewers spot autorouted boards by "smell"; "typical auto router opinion of aesthetics is 'lol'" | [HN](https://news.ycombinator.com/item?id=44544383), [HN](https://news.ycombinator.com/item?id=43501339) [P/C] |
| The last 20% | "DRC compliance only gets you 80 percent... next 15 percent... The last 1 percent is a unicorn"; fixing autorouted work "takes as long … as it does to do it yourself" | [K0balt](https://news.ycombinator.com/item?id=46323727) [P/C] |
| Underestimated problems | Hardware verification "a couple of orders of magnitude harder... there often (usually) is no 'right' solution"; "EMC, EMI, SI, PI and thermal require engineering judgement"; emissions certification "is the other 150%" | [3dB](https://news.ycombinator.com/item?id=49580172), [dmitrygr](https://news.ycombinator.com/item?id=46320726) [P/C] |
| Culture | "NONE of the PCB designers I have worked with... use these tools"; KiCad mod: autorouting "not in the foreseeable future"; Dave Jones: "PCB Autorouters Suck" (2010) | [HN](https://news.ycombinator.com/item?id=12714322), [KiCad forum](https://forum.kicad.info/t/autoroute-is-it-coming-mod-edit-short-answer-is-not-in-the-foreseeable-future-so-nothing-to-see-here/30441), [EEVblog](https://www.eevblog.com/2010/06/12/eevblog-93-pcb-autorouters-suck/) [P/C] |

## Why chip P&R is trusted and PCB autorouting is not

1. Predictive rule decks: chip designers "had to build rule checkers to ensure that, 99.99% of the time, if the rules pass, their design will work"; "nobody looks at the layout". PCB reviewer: "I remember this one time 10 years ago I routed a design like that and we got rejected at the emissions lab" (fpgaminer, [HN](https://news.ycombinator.com/item?id=17240333)) [P/C].
2. Geometry: through-vias obstruct all layers; boards have "4 layers (... only 2 are really used for general routing)" ([bsder](https://news.ycombinator.com/item?id=43501599)); ICs have "dedicated metal for power/ground" and distances so short "circuitous routes still basically don't matter" ([MonMotha](https://www.reddit.com/r/ElectricalEngineering/comments/175ps81/comment/k4m941w/)) [P/C].
3. Coupled problem: "the hard problem is... the combination of the placement and the routing" ([gaze](https://news.ycombinator.com/item?id=29027347)) [P/C].

Use [I]: make passing our checks predict function (chip-P&R model): add return-path, loop-area, connector-orientation, footprint-vs-datasheet and reference-similarity checks ([../verification/critic-stack.md](../verification/critic-stack.md)). Never treat "100% routed" as terminal ([trust-requirements.md](trust-requirements.md)).

## Where routers help: probe vs producer

As a probe [P/C]:
- "a quick autoroute to visualise where routes 'wanted' to go, then iterate over moving parts" ([ImmediateLobster1](https://www.reddit.com/r/AskElectronics/comments/1gpt5n8/comment/lwsy51k/)).
- "use it as an indicator of how well I've placed the components" (obdevel).
- "If it chokes it usually means my board layout and pin assignment were bad" (Maave, [Hackaday](https://hackaday.com/2023/04/14/kicad-autorouting-made-easy/)).
- "50 routing failures" → fix placement, then "tear it up and do hand routing" ([tonyarkles 2018](https://news.ycombinator.com/item?id=16358808)); "a good way to double-check that your floor planning is OK, even if you then rip up" ([2026](https://news.ycombinator.com/item?id=49742345)).

As a producer:
- "All of them work great *given the information available from the schematic* - which isn't *nearly* enough to match a human's routing ability" (triffid_hunter) [P/C].
- "There are no one button auto-routers that work well. For auto-routers to work they need to be guided and take quite a bit of time to setup rooms and rules" (AlexTaradov) [P/C].
- "Group selected routing works well becasue the human is selecting what's likely to route … a manual priority based pre-conditional setup for the routing" ([Dave Jones](https://www.eevblog.com/forum/blog/eevblog-1535-deeppcb-ai-autorouting-tested!/msg4787912/#msg4787912)) [P/E].
- From scratch "rarely over 80%"; finish interactively to >90%, then autoroute the rest (janvi, [KiCad forum](https://forum.kicad.info/t/tensorflow-based-autorouter/15844)) [P/C].
- "beyond 100ish nets, an autorouter is a must," with cleanup (asdf_funky) [P/C].
- "Cadence Specctra / PCB Router is the best autorouter. Most tools … provide input/output translators to Specctra" (FeistyTie5281) [P/C].
- "You should never let an autorouter route 100% of your PCB from scratch … I would definitely favor a good autoplacer over any autorouter" ([SiliconWizard](https://www.eevblog.com/forum/blog/eevblog-1535-deeppcb-ai-autorouting-tested!/msg4794932/#msg4794932)) [P/C].

Use [I]: build the router into the placement loop as a routability oracle; report congestion and failure clusters to the LLM rather than shipping its copper blindly. Spend product effort on placement and constraint capture, not another autorouter.

## Comparisons on real boards

| Test | Result | Source |
|---|---|---|
| Same board and net classes: DeepPCB vs Freerouting vs human | DeepPCB ~2 h, incomplete, 77 vias. Freerouting complete in 10 min, 49 vias. Human 88 vias, many plane stitching | [thinkfat, EEVblog](https://www.eevblog.com/forum/blog/eevblog-1535-deeppcb-ai-autorouting-tested!/msg4788275/#msg4788275) [P/T] |
| Simple 2-layer BLDC driver (2010) | Freerouting beat hand routing (11 vs 18 vias) but ran a trace "between the pins on the clock crystal capacitors" and "used piddly little traces everywhere" | [EEVblog](https://www.eevblog.com/forum/projects/can-you-route-better-than-an-autorouter/msg25704/#msg25704) [P/A] |
| Seven AI tools that produced routed PCBs | All used Freerouting -> [devbisme test](../landscape/kicad-ai-tools-and-mcp-servers.md#independent-hands-on-test-devbisme) | [P/T] |
| CadMust-Neo annealing placer | "HPWL: 597.3 mm → 695.8 mm (16.5% longer)... footprints on footprints, some of them out of the PCB outline" | [Reddit](https://www.reddit.com/r/KiCad/comments/1rq7oe1/comment/o9qc3my/) [P/A] |

## Open questions

- No controlled comparison of human, classical-autorouter and LLM-orchestrated layout on the same board with EMC/SI measurements exists.
- Partial counter-evidence: nctnico reports Altium's autorouter doing well on DDR with good constraints; pedro_uno found a PADS autorouter "guaranteed to work" when driven by a net-class constraint language [P/C].

## Sources

- [practitioner_discussions.md § Q1a–Q1d, Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- See also: [what-good-looks-like.md](what-good-looks-like.md)
