# What a "good" layout looks like: physics, convention and taste

**TL;DR**
- **The expert physics core.** Energy travels in the dielectric fields between a trace and its return path. Every trace is half a transmission line. Rise time, not clock frequency, sets bandwidth. Every signal layer must sit one dielectric away from a continuous reference plane.
- **Practitioner criteria.** Placement first. Ground beats distance. Width only where current flows. Keep margin from rule limits. Clean 45° geometry. Nothing routed through sensitive spots.
- **"Looks good" is necessary but not sufficient.** Neat parallel routing causes crosstalk, so neatness must never override physics.
- **"Taste" has three parts:** physics proxies (check numerically), convention proxies (they set review cost and human editability), and company style (a per-project profile).
- **There is no expert aesthetics rulebook.** The expert aesthetic is a by-product of field containment, manufacturability and reviewability.

## Key facts

Tags: [P] primary; [S] snippet/secondary; [V] vendor; [I] inference. Practitioner quotes add [P/E] expert, [P/C] community opinion, [P/A] anecdote.

### Physics core (experts)

| Expert | Statement | Source |
|---|---|---|
| Hartley | "The most critical item... is the board stack up." "It's really all about rise time." "When you route a trace you're routing half of a transmission line." The 1980s boards' long decoupling traces "worked" only because edges were slow | [Altium podcast](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley) [P/E] |
| Hartley (IPC 2007 deck) | "Highest Frequency of Dig Sig IS NOT the Clock", F(GHz) = 0.50/Tr(ns). "When moving signals between layers, route on either side of the same plane, as much as possible!!!" "When moving signals between 2 Gnd planes, use a transfer (stitching) via VERY near the signal via." "If both planes of a pair are split, don't cross at ANY frequency." "Outer Layers have Poorest Impedance Control and Poorest Cross Talk Control." IC choice: "Paired Power/Ground Pins (Avoid ICs with Corner Power Pins)" and the "Lowest Vcc Level that Satisfies Circuit Needs" | [IPC PDF](https://www.ipc.org/system/files/technical_resource/E14%26S03-02.pdf) [P/E] |
| Hartley | Reference "planes... are also not ground"; he distinguishes three meanings of "ground" | [Sierra blog](https://www.protoexpress.com/blog/how-grounding-controls-noise-and-emi-by-rick-hartley/) [P/E] |
| Bogatin | "The typical schematic shows us nothing about the return path." Aggressor noise exists "only in the traces and white space of the board, not in the schematic." "if your solderless breadboard prototype works, your PCB will probably also work" | [EE Journal](https://eejournal.com/article/matters-of-integrity) [P/E] |
| Bogatin's 20 Rules | #1 answer "it depends" with numbers; #3 avoid whack-a-mole; #4 find the root cause; #7 "always use a continuous return path adjacent to every signal path"; #8 virtual prototypes; #9 "Never perform a measurement or simulation without first anticipating the results"; #13 "Hope can't be part of the design process"; #20 you are "building antennas... not on purpose" | [SI Journal](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers) [P/E] |
| Olney 2024 | "All signal layers should be adjacent to a reference plane"; "place a stitching via as close as possible to each layer transition" | [Beyond Design](https://iconnect007.com/article/143099/beyond-design-highspeed-rules-of-thumb/143096/design) [P] |
| Phil Salmony | "No longer is PCB design simply about 'connecting the dots' but rather an intricate science" | [Altium](https://resources.altium.com/p/how-learn-pcb-design) [P/E] |

### Practitioner "good layout" criteria

- **Placement first**:
  - "The key to good routing is placement" (qu1ck).
  - "A good placement has often autorouted usably well even 30 years ago" (davidsrsb).
  - "PCB design is 90 % finding the optimal placement/rotation" (lbthomsen) [P/C].
- **Ground over distance.** A longer trace over the ground plane beats a short one without it (cedric). In audio, "ground follows signal" (jlm1948) [P/C].
- **Schematic flow.** "group up parts centroids, shove things around until they're roughly in schematic order... readability is king!!" Leave courtyard room for rework access ([EEVblog](https://eevblog.com/forum/eda/standard-component-layouts/msg3796733/#msg3796733)) [P/C].
- **Width where current flows.** VCC wide only where current flows (Piotr). "Engineers preferred larger polygons for power distribution" (Quilter, quoted on [HN](https://news.ycombinator.com/item?id=46299786)) [P/C].
- **Margin, not limits.** An autorouter "will go to the limits imposed to it... more risky for production" ([EEVblog](https://www.eevblog.com/forum/projects/can-you-route-better-than-an-autorouter/msg932635/#msg932635)) [P/C].
- **Clean geometry.** Two 45° turns instead of "10~30 small ones" ([HN](https://news.ycombinator.com/item?id=50117733)) [P/A].
- **Sensitive places stay clear.** Nothing "between the pins on the clock crystal capacitors"; no "power trace under IMU" [P/C].

### Taste vs physics

| Position | Quote | Source |
|---|---|---|
| Looks good, mostly works | "if a PCB design looks good, it will probably work well. However, neatness in routing often leads to unwanted crosstalk as trace segments are routed in parallel for long distances" | [Olney 2012](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design) [P] |
| Necessary, not sufficient | "Pretty looking tracks mean almost nothing when it comes to whether or not a PCB layout is fit for purpose … Mathematically we might define 'looks good' as necessary, but not sufficient" | [AndyC_772, EEVblog](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6215107/#msg6215107) [P/C] |
| Ugly is fine | "There is usually no real need to have a PCB layout readable... If a computer would produce a well working layout that looks uggly, this would be OK" | [Kleinstein](https://www.eevblog.com/forum/blog/eevblog-1535-deeppcb-ai-autorouting-tested!/msg4790522/#msg4790522) [P/C] |
| 45° irrelevant | "I didn't tell Claude to use 45 degree angles … Where it comes to clearance between the traces, Claude's layout is clearly better" | [nctnico](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6338612/#msg6338612) [P/A] |
| Physics check on corners | At −15 dB return loss, "a 20.5 mil wide trace is transparent below 25 GHz … 90° corners are not a signal integrity crisis" | [Flux](https://www.flux.ai/p/blog/pcb-design-mistakes) [P] |
| Convention decides acceptance | A tool that ignores convention "produces output engineers reject on sight... 'looks right' varies by company"; acid traps and fiber-weave skew are real physics | [Quilter blog](https://www.quilter.ai/blog/pcb-autorouter-was-the-right-idea) [V] |
| Editability | On any-angle output: "a human going in a selectively re-routing is going to have a painful experience" | [thm_w](https://www.eevblog.com/forum/blog/eevblog-1535-deeppcb-ai-autorouting-tested!/msg4807124/#msg4807124) [P/C] |
| Orientation | "'which way is up' is an unsolved problem right now" | [crote, HN](https://news.ycombinator.com/item?id=49743354) [P/C] |
| Aesthetics serve function | Aesthetic tips "which in turn also benefit functionality, manufacturability" | [Phil's Lab #84](https://home.fedevel.com/blog/aesthetic-pcb-design-tips-phils-lab-84) [P/E] |
| Readability matters | "Readability of the traces is also a goal, isn't it?" | [golden_labels](https://www.eevblog.com/forum/blog/eevblog-1535-deeppcb-ai-autorouting-tested!/msg4787999/#msg4787999) [P/C] |
| Art | "Board layout is an artform. Autorouters are not artists" (TwoSpoons); "a curious blend of artistic skill and a working knowledge of electronics" (nixiebunny) | [P/C] |
| Templates | Distrust app notes ("Wrong until Proven Right!") and open-source designs (Bogatin on the Arduino Uno R3) | [P/E] |

## Recommendations for our system

- **Hard field-containment checks.** For every critical net, check for an adjacent continuous reference plane, no split crossings, a transfer via within distance d at each layer change, and loop area. These form the "physics" half of a figure of merit [I].
- **Three score channels** [I]:
  - physics, which gates;
  - convention, a soft term that tracks review cost and editability;
  - style, a per-company profile stored as data.
- **Pair every neatness term with a coupling-length penalty**, per Olney's caveat. Measurable metrics are in [../verification/looks-right-metrics.md](../verification/looks-right-metrics.md) [I].
- **Default to human-editable geometry**: 45° only, few turns, no any-angle routes, plus consistent orientation and silkscreen [I].
- **Never treat an app note or open-source layout as ground truth**; run it through the critics ([layout-reuse.md](layout-reuse.md)) [I].

## Conflicts and open questions

- How much reviewers weight convention against physics is unquantified, and no per-company style guides were found.
- No study links layout aesthetics to measured SI/EMC performance or reviewer acceptance.
- Hartley/Bogatin talk transcripts and Phil's Lab placement videos were not retrievable (YouTube blocked); only chapter lists and slides were read.

## Sources

- research notes: [practitioner_discussions.md § Q3, Q4a, Q5c](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- research notes: [expert_workflow_and_checklists.md § Q1 physics framing, Q6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)

See also: [delegation-and-expert-review.md](delegation-and-expert-review.md), [../verification/looks-right-metrics.md](../verification/looks-right-metrics.md), [../rules/si-fundamentals.md](../rules/si-fundamentals.md)
