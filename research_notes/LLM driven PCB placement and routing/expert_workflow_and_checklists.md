# Expert PCB layout workflow and design-review checklists (to encode as an LLM-driven KiCad planner + automated critics)

> Research notes compiled 2026-10-20. **Access limits during this research:** direct page fetching (WebFetch/curl) was blocked for almost all non-GitHub/GitLab hosts (Altium, KiCad forum, iConnect007, Atlassian wikis, TI, YouTube). The shared web-search budget also ran out partway through. Findings from vendor and blog pages therefore come from **search-result summaries** of those pages. The URL is cited, but the full text was not read, so treat exact wording as approximate. **Primary sources read in full:** five GitHub checklist repos (azonenberg, grosdode, Pikafu, henrikh, jnoss), the KiCad documentation source on GitLab (DRC, custom rules, design blocks, multichannel, editing, getting-started), and one open-source LLM/KiCad skill pack (l3wi/claude-eda) as prior art.

---

## Q1. What does the expert layout workflow look like, step by step, with its decision points, reasoning, placement-routing iteration and time split?

### Takeaway
Practitioner sources agree on a constraint-first order. First: mechanical outline, fixed parts and stackup/rules. Then: floorplan by function, critical parts, decoupling, the remaining parts, and a placement sanity check. Routing starts only after that: fanout, critical nets, planes, bulk, tuning, stitching. DRC/DFM, silkscreen and outputs come last. Placement is the dominant, iterative activity: experts watch the ratsnest, test routability, and co-design BGA fanout with placement. "90% placement / 10% routing" is folklore, not a measurement.

### Cited Findings

**Overall ordering (multiple independent sources)**
- Placement order used by Robert Feranec (FEDEVEL, motherboard designer): start with fixed items (board shape, mounting holes, connectors), then CPU and memories, then other chips, then power-supply parts, and finally small components — [FEDEVEL DesignHelp forum, "Placement" thread](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629); [mirror](https://courses.fedevel.com/forum/schematic-design-pcb-layout/4626-placement). (Search summary. A fixed "five-group" framing came from the asker, not Feranec.)
- Feranec does **fanout and placement at the same time**. He first places a few parts under the CPU to judge how much space is needed, then moves them out, places the vias, and brings components back in from the middle — [FEDEVEL forum](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629).
- Feranec tip #95: place *all* components on the board before you start routing, because it is very hard to add components into already-routed areas — [FEDEVEL Tip 095](https://courses.fedevel.com/blog/tip-095-you-may-want-to-place-all-the-components-on-the-board-before-you-start-doing-layout).
- Feranec on autorouting: "We never use autorouter." He routes interactively — [FEDEVEL forum, "auto or interactive route"](https://fedevel.com/forum/imx6-rex-tiny-rex-open-rex/3198-auto-or-interactive-route).
- Feranec's Sierra Circuits workshop ran in this order: stackup → placement → BGA fanout → layout → testing. It also covered crosstalk and high-speed rules. On impedance he said a calculator is useful but you should always talk to your manufacturer — [Sierra/ProtoExpress workshop post](https://www.protoexpress.com/blog/sierra-pcb-layout-design-workshop-robert-feranec/); [workshop listing](https://www.protoexpress.com/blog/workshop-pcb-layout-design-engineering/).
- Memory chips placed too close together leave no room to route between them. A power supply's transistor, inductor and capacitors should sit close together — [FEDEVEL forum](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629).
- JLCPCB's 2026 placement guide gives the sequence: mechanical constraints → key ICs → supporting passives → secondary components → a "placement sanity check before any routing begins" — [JLCPCB placement guide](https://jlcpcb.com/blog/pcb-component-placement-guide-2026).
- Flux: define the PCB's shape and size from mechanical/enclosure constraints first. Then organize components into functional blocks, e.g. group power-management parts and keep them away from sensitive signal processing — [Flux component placement tutorial](https://docs.flux.ai/tutorials/component-placement).
- KiCad's official Getting Started guide orders it as board outline on Edge.Cuts → place footprints → route → DRC → fabrication outputs. Its placement considerations are, in order:
  - parts with exact location requirements (connectors, indicators, buttons);
  - electrical requirements (bypass caps near IC power pins, sensitive analog far from digital);
  - courtyards should not intersect;
  - otherwise place for ease of routing, using the ratsnest.
  
  Source: [KiCad Getting Started (doc source)](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/getting_started_in_kicad/getting_started_in_kicad.adoc).
- MIT 2.996 lab handout: place all components before routing any traces, and use the rat's-nest lines plus the schematic to judge which placement makes routing easiest. Keep decoupling caps near their components — [MIT OCW 2.996 lab handout (mirror)](https://mitocw.ups.edu.ec/courses/mechanical-engineering/2-996-biomedical-devices-design-laboratory-fall-2007/labs/lab_handout3.pdf).
- Pikafu's best-practice list says to define size, shape and mechanical features before starting layout, and to start with a small layer count and increase it only if needed — [Pikafu/pcb_design](https://github.com/Pikafu/pcb_design).
- grosdode's checklist:
  - import all design rules from your PCB manufacturer first;
  - place connectors first, in reachable places (right-angle connectors need board-edge placement, latching connectors need thumb clearance, model the mating connector in 3D);
  - place mounting holes;
  - place parts on a coarse grid (1 mm / 1.27 mm).
  
  Source: [grosdode/PCB-design checklist](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md).

**Routing order**
- Practitioner guides agree that you define rules first (width, spacing, via sizes, diff-pair and length-matching rules) and then route the most constrained nets first: clocks, differential pairs, sensitive analog and power-switching loops. The remaining design is then built around those tracks. Power/ground planes come next, followed by general low-speed signals, then length tuning and verification (DRC, DFM, netlist compare, impedance, copper balance, mask, assembly clearance). Sources: [JLCPCB routing rules](https://jlcpcb.com/blog/pcb-routing-rules-best-practices); [JLCPCB layout process guide 2026](https://jlcpcb.com/blog/pcb-layout-process-guide-2026-mastering-pcb-design); [electronics-notes PCB layout & routing](https://www.electronics-notes.com/articles/analogue_circuits/pcb-design/pcb-layout-routing.php); [PCD&F June 2019 "PCB Guided Insights"](https://www.qgdigitalpublishing.com/article/PCB+Guided+Insights/3388181/589425/article.html); [Cadence "What is PCB layout"](https://www.cadence.com/en_US/home/explore/what-is-pcb-layout.html). (The search summary blended these; individual attribution is not certain.)
- A warning from the same set: don't let easy routes consume the space first. If the last ~10% of routing contains critical signals, the job "will most certainly turn into defeat and a complete do-over" — same sources as above, most likely [PCD&F 2019](https://www.qgdigitalpublishing.com/article/PCB+Guided+Insights/3388181/589425/article.html).
- These sources differ on whether planes/power come before or after critical routing. The common rule is that the most constrained nets get priority — [JLCPCB process guide](https://jlcpcb.com/blog/pcb-layout-process-guide-2026-mastering-pcb-design); [electronics-notes](https://www.electronics-notes.com/articles/analogue_circuits/pcb-design/pcb-layout-routing.php).
- Length-tuning tolerances come from the protocol. One cited example is ±5 mil for DDR3, with tighter values for PCIe Gen5/6 — [JLCPCB routing rules](https://jlcpcb.com/blog/pcb-routing-rules-best-practices).

**Physics framing that drives decisions (Hartley, Bogatin)**
- Rick Hartley: the board stackup is the most critical item and the one people most often get wrong. Energy travels in the dielectric between traces and planes, not in the copper — [Altium: stack-up best practices with Rick Hartley](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley).
- Hartley: a signal line should sit one dielectric away from its ground plane to contain fields and control return current. Otherwise grounding problems follow — [EE Journal "Matters of Integrity"](https://eejournal.com/article/matters-of-integrity); [ProtoExpress on Hartley's EMI recommendations](https://www.protoexpress.com/blog/rick-hartley-pcb-design-recommendations-to-minimize-emi/).
- Hartley: routing over splits in ground planes increases EMI. He has publicly disowned parts of his own older stack-up paper ("not good ideas ... ignore this paper") — [ProtoExpress](https://www.protoexpress.com/blog/rick-hartley-pcb-design-recommendations-to-minimize-emi/); [AltiumLive Frankfurt 2019 keynote write-up](https://design.iconnect007.com/article/120662/altiumlive-frankfurt-2019-rick-hartley-keynote/120665/design?page=2). (Search summary; which of these pages holds the quote is not certain. An [IPC 2007 grounding presentation](https://www.ipc.org/system/files/technical_resource/E14%26S03-02.pdf) also came up in the same search; its authorship was not verified.)
- Eric Bogatin groups SI/PI/EMI problems into six families and attributes ground bounce, power-path problems and EMI largely to poor return-path management — [EE Journal "Matters of Integrity"](https://eejournal.com/article/matters-of-integrity).
- The "Beyond Design" column says that at high speed, return current flows in the reference plane directly beneath the trace (the lowest-inductance path). Stitching vias should give return current a path between ground planes — [iConnect007 Beyond Design: High-speed Rules of Thumb](https://iconnect007.com/article/143099/beyond-design-highspeed-rules-of-thumb/143096/design).

**Iteration between placement and routing**
- A KiCad forum user describes placement as "an iterative process. I try to work out the best placement for the major components, and watch what happens to the rats nest" — [KiCad forum: Strategy to use for placing components](https://forum.kicad.info/t/strategy-to-use-for-placing-components/23682).
- Autodesk EAGLE guidance has two parts:
  - The placement goal is to minimize the length and crossing of airwires.
  - Sanity test: run the autorouter after placement. If it completes less than ~85%, spend more time on placement.
  
  Sources: [Autodesk: PCB layout basics – component placement](https://www.autodesk.com/products/eagle/blog/pcb-layout-basics-component-placement/); [Autodesk: Top 10 placement tips](https://www.autodesk.com/products/fusion-360/blog/top-10-pcb-component-placement-tips-pcb-beginner/).
- Placement should also allow for inspection and rework, not just routing — [ICD (Barry Olney) "Interactive Place & Route," PCB Design Dec 2012](https://www.icd.com.au/articles/Interactive_Place_&_Route_PCBDesign-Dec2012.pdf); see also [iConnect007 Beyond Design: Interactive Placement and Routing Strategies](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design).
- Staged reviews put formal iteration checkpoints between phases: pre-layout review, component placement review, critical routing review — [VSE layout checklist](https://www.vse.com/blog/a-pcb-layout-checklist-for-error-free-manufacturing/). Flux describes schematic → layout (placement, routing, thermal, stackup) → DFM reviews as separate passes, so each class of error is isolated — [Flux design review process](https://www.flux.ai/p/blog/pcb-design-review-process).

**Time split (placement vs routing)**
- "PCB design is 90% placement and 10% routing" is a common saying, repeated by Autodesk — [Autodesk EAGLE First Flights webinar](https://www.autodesk.com/products/fusion-360/blog/eagle-first-flights-webinar-surveying-part-placement/); [PCB Power social post](https://social.pcbpower.com/we-often-hear-this-saying-in-the-electronics-community-pcb-design-is-90-placement-and-10-routing-we-always-2344200531386298630).
- Siemens says "studies have shown that a majority of design time is spent on placement and routing" but cites no studies. Its "up to 80%" figure is a marketing claim about how much automation reduces layout time — [Siemens blog 2019](https://blogs.sw.siemens.com/electronic-systems-design/2019/04/02/reduce-design-time-using-routing-automation-part-1/); [Siemens blog 2022](https://blogs.sw.siemens.com/electronic-systems-design/2022/11/23/pcb-design-physical-layout).
- DeepPCB (an AI-routing vendor) disputes that routing is the bottleneck. It names constraint definition, review cycles and iteration as larger time sinks — [DeepPCB: timeline compression](https://deeppcb.ai/pcb-design-timeline-compression/).

**Phil's Lab**
- Phil's Lab #70 is a full schematic + PCB design review of a KiCad wireless keyboard adapter, covering common errors and best practices — [FEDEVEL repost of Phil's Lab #70](https://fedevel.com/blog/design-review-schematic-pcb-phils-lab-70). Transcript content was not accessible.

#### Ordered workflow model (synthesized; each step backed by the cited sources)

| # | Stage | What experts do | Decision points / reasoning | Exit criterion | Typical loop-back | Sources |
|---|---|---|---|---|---|---|
| 0 | Pre-layout intake | Schematic signed off. Constraints captured: net classes, impedance, currents, voltages, critical nets. Fab/assembler capabilities loaded as rules | Which nets are critical? Which fab/class? Rules are set before any routing | Clean ERC/sign-off; rules = fab capability | — | [azonenberg](https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md), [grosdode](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md), [Pikafu](https://github.com/Pikafu/pcb_design), [JLC routing](https://jlcpcb.com/blog/pcb-routing-rules-best-practices), [VSE](https://www.vse.com/blog/a-pcb-layout-checklist-for-error-free-manufacturing/) |
| 1 | Outline & mechanics | Board outline, mounting holes, keepouts, height zones, connector positions taken from the enclosure. Use round dimensions and a coarse grid | Enclosure drives size. Connectors with latches need clearance. Right-angle parts go at the edge | Outline closed; holes/keepouts placed; 3D fit plausible | Back here if board area proves insufficient (Step 8) | [Pikafu](https://github.com/Pikafu/pcb_design), [Flux](https://docs.flux.ai/tutorials/component-placement), [grosdode](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md), [Feranec](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629), [henrikh "Floorplan"](https://github.com/henrikh/pcb-checklist) |
| 2 | Stackup & layer count | Pick the minimum layer count, build a stackup with every signal layer next to a plane, confirm with the fabricator | Hartley: stackup is the most critical decision. Rules of thumb: 70% channel use, autoroute feasibility | Stackup + impedance widths agreed with the fab | Back from Step 8/12 if routing density is too high | [Hartley/Altium](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley), [NextPCB](https://www.nextpcb.com/blog/how-many-layers-can-a-pcb-have), [VSE stackup](https://www.vse.com/blog/multilayer-pcb-stackup-planning/), [Feranec workshop](https://www.protoexpress.com/blog/sierra-pcb-layout-design-workshop-robert-feranec/) |
| 3 | Fixed-position parts | Connectors, UI parts (LEDs/buttons outward-facing), heatsinks, test/debug headers | Usability and the mechanical standard (keying, orientation) | All fixed parts locked | — | [azonenberg](https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md), [KiCad Getting Started](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/getting_started_in_kicad/getting_started_in_kicad.adoc), [grosdode](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md) |
| 4 | Floorplan by function / signal flow | Group by schematic block. Separate power, analog, digital and RF regions. Order blocks along the signal path from connectors inward | SMPS away from analog. Interface ICs/ESD by their connectors. Shortest critical paths | Block regions assigned | Moves again after Step 5/8 | [Flux](https://docs.flux.ai/tutorials/component-placement), [grosdode](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md), [azonenberg](https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md), [henrikh](https://github.com/henrikh/pcb-checklist), [KiCad select-by-sheet](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc) |
| 5 | Critical components | CPU/memories/BGAs (with trial fanout), power-stage hot loops, crystals, RF/antenna, terminations | Hot loop area; crystal near pins; routing channels between memories; datasheet layout examples | Critical parts placed and oriented for escape | Iterate with Step 9 (concurrent fanout) | [Feranec](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629), [TI layout guidelines](https://ti.com/document-viewer/TPS61178/datasheet/layout-guidelines-slvsda71918), [henrikh](https://github.com/henrikh/pcb-checklist), [jnoss](https://github.com/jnoss/pcb-checklist) |
| 6 | Decoupling | Caps at power pins, smallest value closest, low-inductance via mounting | One cap per pin; same layer as the IC where possible | Each power pin has an assigned cap within the threshold | — | [azonenberg](https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md), [Pikafu](https://github.com/Pikafu/pcb_design), [jnoss](https://github.com/jnoss/pcb-checklist), [KiCad editing tip](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc) |
| 7 | Remaining parts | Pull-ups, LEDs, misc passives near their users; consistent orientation; grid | All parts placed before routing | Everything placed; no courtyard overlaps | — | [Feranec tip 095](https://courses.fedevel.com/blog/tip-095-you-may-want-to-place-all-the-components-on-the-board-before-you-start-doing-layout), [JLC placement](https://jlcpcb.com/blog/pcb-component-placement-guide-2026), [MIT handout](https://mitocw.ups.edu.ec/courses/mechanical-engineering/2-996-biomedical-devices-design-laboratory-fall-2007/labs/lab_handout3.pdf) |
| 8 | Placement review / routability check | Inspect the ratsnest. Quick autoroute trial (≥~85%). Formal placement review | Is the layer count adequate? Are channels big enough? Rework access? | Review passed | Fail → Steps 4–7, or Step 2 (add layers) | [Autodesk](https://www.autodesk.com/products/eagle/blog/pcb-layout-basics-component-placement/), [VSE stackup](https://www.vse.com/blog/multilayer-pcb-stackup-planning/), [VSE checklist](https://www.vse.com/blog/a-pcb-layout-checklist-for-error-free-manufacturing/), [ICD 2012](https://www.icd.com.au/articles/Interactive_Place_&_Route_PCBDesign-Dec2012.pdf) |
| 9 | Fanout / escape | BGA/QFN escape vias, decap vias under BGAs | Feranec co-designs this with Step 5 | All dense pins escaped | → Step 5 if escape fails | [Feranec](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629), [Feranec workshop](https://www.protoexpress.com/blog/sierra-pcb-layout-design-workshop-robert-feranec/) |
| 10 | Critical routes | Diff pairs, clocks, RF, power loops, sensitive analog, routed interactively | Keep return paths continuous; minimize layer changes; return vias | Critical nets routed and meeting rules | → Step 5 if impossible | [JLC routing](https://jlcpcb.com/blog/pcb-routing-rules-best-practices), [electronics-notes](https://www.electronics-notes.com/articles/analogue_circuits/pcb-design/pcb-layout-routing.php), [azonenberg](https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md), [Hartley](https://www.protoexpress.com/blog/rick-hartley-pcb-design-recommendations-to-minimize-emi/) |
| 11 | Planes / pours | Solid GND reference(s); power planes/pours; avoid splits and antipad slots | Split only with justification | Planes continuous under critical nets | — | [Hartley](https://www.protoexpress.com/blog/rick-hartley-pcb-design-recommendations-to-minimize-emi/), [azonenberg](https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md), [grosdode](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md) |
| 12 | Bulk routing | Remaining nets, interactive (Feranec never autoroutes) | Don't let easy nets block later ones | 0 unrouted | → Step 7 or Step 2 | [Feranec](https://fedevel.com/forum/imx6-rex-tiny-rex-open-rex/3198-auto-or-interactive-route), [PCD&F 2019](https://www.qgdigitalpublishing.com/article/PCB+Guided+Insights/3388181/589425/article.html) |
| 13 | Length/skew tuning | Meanders per protocol budget | Tolerances from the interface spec | Length/skew rules pass | — | [JLC routing](https://jlcpcb.com/blog/pcb-routing-rules-best-practices), [azonenberg](https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md) |
| 14 | Stitching / fencing | GND stitching, return vias at layer changes, RF via fences (≤λ/8) | Fence pitch set by frequency | Stitch rules satisfied | — | [Pikafu](https://github.com/Pikafu/pcb_design), [azonenberg](https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md), [Beyond Design HS rules](https://iconnect007.com/article/143099/beyond-design-highspeed-rules-of-thumb/143096/design) |
| 15 | DRC / DFM / parity | DRC clean, schematic parity, DFM review against fab capability | Waivers reviewed | 0 errors; waivers signed | → local repair | [KiCad DRC docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_inspecting.adoc), [MacroFab](https://macrofab.com/blog/five-tips-to-clean-up-your-layout/), [bestpcbs DFM](https://www.bestpcbs.com/blog/2026/07/pcb-design-for-manufacturability-checklist/) |
| 16 | Silkscreen, assembly, outputs | Silk cleanup, fiducials, fab/assembly drawings, re-run zone fill + DRC, export Gerber + drill together, independent viewer check | — | Outputs verified | — | [azonenberg](https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md), [Pikafu](https://github.com/Pikafu/pcb_design) |
| 17 | Final review & sign-off | Per-IC datasheet review; functional requirements review; reviewer sign-off tied to a commit | DRC can pass a functionally wrong board | Signed off | → any step | [UWARG](https://uwarg-docs.atlassian.net/wiki/spaces/EL/pages/2173501609), [Altium perils](https://resources.altium.com/p/how-to-navigate-the-perils-of-pcb-design-review), [UW Rocketry](https://uwaterloo.atlassian.net/wiki/spaces/ROCKETRY/pages/43024155641/Design+Reviews) |

### Inferences
- The workflow is not linear. It is a **constraint-propagation loop with heavy front-loading**: steps 0–8 fix most of the outcome, and the cited sources put almost all of the expert's judgment into placement (Feranec's concurrent fanout, ratsnest watching, the 85% routability test). An automated system should therefore spend most of its search/compute budget on placement and use cheap routability estimates as the inner-loop objective.
- "Critical routes first" and "place everything before routing" only look contradictory. Experts place all parts, then route in priority order, and loop back to placement when critical routes fail. This maps onto an explicit backtracking state machine (see the final section).
- Feranec doing BGA fanout during placement suggests the planner should treat **escape feasibility** as a placement-time constraint for dense packages, not a post-placement step.
- The 90/10 folklore and the DeepPCB counterpoint fit together: placement takes most of the *designer's attention*, while review/constraint/iteration cycles take most of the *calendar time*. Both point to automated critics (fast review) as a high-leverage target.

### Gaps
- No transcripts of Rick Hartley, Eric Bogatin or Phil's Lab talks on *placement order specifically* were accessible. Hartley/Bogatin material found was about stackup and return paths. Phil's Lab's own checklist (if one exists) was not found.
- No measured data on time split (placement vs routing) was found. Every number is folklore or vendor marketing.
- Book contents (Ritchey "Right the First Time", Archambeault, Robertson, "Complete PCB Design Using OrCAD") could not be read. Only bibliographic details are known (see Q2).
- I found no Cadence or Sierra Circuits "layout process" page text beyond search summaries. The Sierra Circuits checklist items themselves were not retrievable ([ProtoExpress design review & cleanup](https://www.protoexpress.com/blog/how-to-perform-pcb-design-review-and-layout-clean-up/) is the closest).

---

## Q2. How do experts decide board size, layer count and stackup?

### Takeaway
Board size is almost always set by the enclosure/mechanical envelope, not chosen freely. Layer count is the minimum that gives every high-speed signal a continuous reference plane, gives each power domain enough copper, and lets fine-pitch parts escape, with margin when routing density is high. Experts design the stackup *with* the fabricator, and Hartley calls it the most important (and most often botched) decision.

### Cited Findings
- Define size, shape and mechanical features before layout. Start with a small layer count and increase it if needed. You don't need GND between every power plane, but every signal layer needs at least one GND reference. Consider how efficiently the board fits a standard panel — [Pikafu/pcb_design](https://github.com/Pikafu/pcb_design).
- Use "easy values for board dimensions (100 mm instead of 98.95231651313513 mm)" — [grosdode checklist](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md).
- Board shape and size come from mechanical constraints and enclosure requirements — [Flux placement tutorial](https://docs.flux.ai/tutorials/component-placement).
- NextPCB rule of thumb: choose the minimum layer count that gives every high-speed signal a continuous reference plane, enough copper per power domain and clean escape for fine-pitch parts. Then add one pair of layers as margin if routing density exceeds 70% of available channels — [NextPCB](https://www.nextpcb.com/blog/how-many-layers-can-a-pcb-have).
- VSE: if the layer count is adequate, an autorouter should nearly be able to complete routing on its own. Fewer layers mean tighter manufacturing tolerances and more SI risk. Cost matters, especially in volume — [VSE multilayer stackup planning](https://www.vse.com/blog/multilayer-pcb-stackup-planning/).
- Typical ranges: complicated boards with FPGAs, SoCs or RF often need 6–8+ layers; simple designs need 2–4 — [JLCPCB multilayer stackup](https://jlcpcb.com/blog/multilayer-pcb-stackup).
- Keep the stackup symmetric to limit warpage, avoid adjacent signal layers, use solid ground planes, and avoid more than 4 lamination cycles — [ProtoExpress stack-up design guide](https://www.protoexpress.com/pcb-design-guides/pcb-stack-up-design-guide/); [JLCPCB multilayer stackup](https://jlcpcb.com/blog/multilayer-pcb-stackup).
- A KiCad practitioner picks layer count from routing complexity and board thickness from mechanical constraints, then uses the fab's standard stackup or asks the fab for a custom one — [KiCad forum: About stack up selection](https://forum.kicad.info/t/about-stack-up-selection/21123).
- Hartley: stackup is the most critical item and is often wrong. Keep traces one dielectric from their plane. Design around the fab's real dielectrics/copper weights and adjust trace width to hit impedance — [Altium/Hartley](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley); [EE Journal](https://eejournal.com/article/matters-of-integrity); [ProtoExpress/Hartley](https://www.protoexpress.com/blog/rick-hartley-pcb-design-recommendations-to-minimize-emi/).
- Checklists require the stackup to be verified with the manufacturer and specified in fab notes, along with confirmation that copper thickness matches the target manufacturer — [azonenberg layout checklist](https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md); [Altium PCB design and review checklist (Mark Harris)](https://resources.altium.com/p/pcb-design-and-review-checklist).
- Feranec: use impedance calculators, but always communicate with your manufacturer — [ProtoExpress workshop post](https://www.protoexpress.com/blog/sierra-pcb-layout-design-workshop-robert-feranec/).
- Lee Ritchey & John Zasio, *Right The First Time*: a practical high-speed PCB/system design handbook in two volumes (Vol 1 fundamentals; Vol 2 detailed design/manufacturing steps), with 48 short chapters in 288 pages — [Electronic Design review](https://www.electronicdesign.com/technologies/components/interconnects/article/21775386/right-the-first-time); [Vol 2](https://www.electronicdesign.com/boards/right-first-time-volume-2). (Search summaries also report that Ritchey argues letting the fabricator design the stackup no longer works and that you should treat the fab as a design partner. The underlying 2012 article could not be identified, so this is low confidence.)
- Archambeault, *PCB Design for Real-World EMI Control* (Springer, 2002, 244 pp, SECS vol 696; with J. Drewniak): 13 chapters + 1 appendix. Ch 1 is an EMI/EMC overview for PCBs, Ch 2 EMC fundamentals, Ch 4 "The Ground Myth" — [Springer](https://link.springer.com/978-1-4020-7130-0); [IEEE EMC Society newsletter review](https://ewh.ieee.org/soc/emcs/acstrial/newsletters/spring08/book_review.html).
- Prior-art LLM skill pack (claude-eda) encodes a layer-count table:
  - 2-layer for simple/LDO/I2C/SPI boards;
  - 4-layer (SIG-GND-PWR-SIG) as "the safe default" for most MCU projects, switchers, USB/Ethernet and WiFi/BLE;
  - 6-layer for DDR, PCIe, GbE and dense mixed-signal boards.
  
  It also lists "2-layer with USB: can't achieve 90Ω differential impedance" as a common mistake — [l3wi/claude-eda LAYER-COUNT-DECISION.md](https://github.com/l3wi/claude-eda/blob/main/templates/claude/skills/eda-architect/reference/LAYER-COUNT-DECISION.md). (Caution: that USB claim is not sourced and is too broad, because 90 Ω coupled lines/coplanar structures can be built on 2-layer boards. It shows why LLM-encoded heuristics need provenance.)

### Inferences
- A usable **board-size estimator** for an agent, derived from the sources above rather than published: (a) if an enclosure exists, the outline is an input, not a variable; (b) otherwise estimate the required area as Σ(courtyard areas) ÷ target utilization, plus perimeter keepouts (~3 mm handling border per grosdode) and connector edge length, then round up to "easy" dimensions and check panel efficiency (Pikafu).
- **Layer count** fits a generate-and-test loop: start at the minimum implied by the high-speed/power requirements (NextPCB criteria), run a placement + quick routability trial (VSE/Autodesk autoroute heuristics), and add a layer pair if channel utilization is >70% or completion is low.
- Stackup generation should be **fab-template-driven** (pick from the fab's standard stackups, per the KiCad forum practitioner and Feranec's "talk to the manufacturer"), with a rule that every signal layer must be adjacent to a plane (Hartley, Pikafu).

### Gaps
- No rigorous, published board-size decision method was found.
- No quantitative cost-vs-layer-count model from a primary source was retrieved.
- Contents of Robertson's *Printed Circuit Board Designer's Reference: Basics* and *Complete PCB Design Using OrCAD* were not accessible.

---

## Q3. How do experts use schematic hierarchy and reuse layouts (datasheet/eval-board layouts, channel copies, snippets, KiCad design blocks, multichannel)?

### Takeaway
Experts use the schematic's functional structure (sheets/blocks) as the floorplan's skeleton and copy known-good sub-layouts. KiCad now supports this directly: selection by hierarchical sheet, Pack-and-Move clustering, **design blocks** (saved schematic and/or layout fragments) and **multichannel Repeat Layout**, which copies one routed reference channel to topologically identical channels after an isomorphism check. Datasheet "Layout Guidelines/Layout Example" sections are the standard reference layout for each IC, and reviewers check each IC's layout against them.

### Cited Findings
**Schematic structure → layout**
- KiCad can select footprints by schematic sheet (right-click → Select → Items in Same Hierarchical Sheet). Cross-selection from the schematic selects the matching footprints. **Pack and Move Footprints (P)** packs a selection into a block, and **Move Individually (Ctrl+M)** places selected parts one by one. The doc's own tip: select the bypass caps in the schematic, switch to PCB, then Move Individually to drop each near its IC. KiCad also has Auto-Place, which tries to place footprints to simplify ratsnest connections — [KiCad PCB editing docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc).
- When updating the PCB from the schematic, footprints can be added to PCB groups if their symbols are grouped — [KiCad schematic-to-PCB docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_schematic_to_pcb.adoc).
- Divide the schematic into logical segments with labels. Segment borders are good places for 0 Ω resistors and/or test points — [grosdode](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md). Schematics should flow left → right, top → bottom — [Pikafu](https://github.com/Pikafu/pcb_design). Symbols should reflect function while "board layout should reflect physical reality" — [henrikh checklist](https://github.com/henrikh/pcb-checklist).

**KiCad design blocks (layout reuse)**
- Design blocks save part of a schematic and/or layout for reuse within or across projects. They live in libraries (`.kicad_blocks` folders) in global/project library tables. A block can hold a schematic fragment, a layout fragment, or both. "Typically, design blocks are created first as a schematic fragment, with layout added later." If a block contains both, its saved layout can be applied to the footprints that correspond to the symbols of a placed schematic block — [KiCad PCB design blocks docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_design_blocks.adoc); [schematic design blocks docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/eeschema/eeschema_design_blocks.adoc).
- Placement options: place repeated copies, **place as group** (the group keeps a link to the source block; some functions need this), and keep annotations. Layout blocks can be placed directly without schematic linkage, e.g. a mounting-hole pattern. A placed block can be edited and written back with "Update Design Block from Selection" or "Save to Linked Design Block" — [KiCad PCB design blocks docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_design_blocks.adoc).

**KiCad multichannel layout**
- Purpose: replicate the layout of repeated sub-circuits (audio mixer channels, multi-output supplies, LED driver channels). You place and route one *reference* channel, then **Repeat Layout** copies placement and routing to the *target* channels — [KiCad multichannel docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_multichannel.adoc).
- Channels can be defined by repeated hierarchical sheets (the recommended approach, since instantiating the same sheet file guarantees identical circuitry), by **component classes**, or by named **groups**. Equivalent channels need the same symbol count, the same reference prefixes per corresponding symbol, the same footprints and equivalent connections. Different values do not break equivalence — [KiCad multichannel docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_multichannel.adoc).
- "Generate Placement Rule Areas" builds one rule area per selected sheet/class/group: a convex hull around its footprints with a margin, rectified into an axis-aligned 90° polygon and named `auto-placement-area-<source>`. Repeat Layout runs a **topology check that searches for an isomorphism** between reference and each target before copying. Items copy only on layers enabled in both rule areas — [KiCad multichannel docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_multichannel.adoc).
- The cited files are the current `master` KiCad documentation sources. This research did not verify which KiCad release first shipped each feature.

**Datasheet / reference-layout reuse**
- TI datasheets have dedicated "Layout Guidelines" sections. Examples: minimize the high-di/dt loop (switch FET, rectifier FET, output cap); minimize SW-node trace length/area with a ground plane under the regulator; keep FB away from SW — [TPS61178 layout guidelines](https://ti.com/document-viewer/TPS61178/datasheet/layout-guidelines-slvsda71918); [TPS55330 layout guidelines](https://www.ti.com/document-viewer/TPS55330/datasheet/layout-guidelines-slvsbx81345).
- TI app note SLVAFJ3 (LM5177 family) lays out a structured layout procedure: identify critical paths → optimize power-stage hot loops → separate sense lines from power planes → route gate-drive returns → separate AGND/PGND → thermal vias → layout example — [TI SLVAFJ3](https://www.ti.com/document-viewer/lit/html/SLVAFJ3/GUID-90181CF4-7939-4962-A565-7204ECA6A0CF). TI AN-1229 notes that a switching converter design is only as good as its layout — [TI SNVA054](https://ti.com/lit/pdf/snva054).
- Review practice: check each significant IC circuit (regulators, LDOs, MCUs, transceivers) against the datasheet's layout recommendations, possibly with a separate reviewer per IC — [UWARG layout review checklists](https://uwarg-docs.atlassian.net/wiki/spaces/EL/pages/2173501609); [UW Rocketry design reviews](https://uwaterloo.atlassian.net/wiki/spaces/ROCKETRY/pages/43024155641/Design+Reviews). "Re-read all datasheets for layout requirements – e.g., antenna spacing from ground plane, copper land for heatsinking" — [jnoss checklist](https://github.com/jnoss/pcb-checklist).
- "If making multiple similar boards, follow same convention for connector layout/orientation on each" — [jnoss](https://github.com/jnoss/pcb-checklist).

### Inferences
- For an agent: **hierarchical sheet = placement cluster = candidate rule area.** KiCad's own rule-area generator (convex hull → rectilinear polygon per sheet) is a ready-made floorplan primitive, and Repeat Layout's isomorphism check is a ready-made "is this channel a copy?" detector.
- Design blocks give the agent a **layout memory**. Successful sub-layouts (buck stage, USB-C + ESD, crystal + MCU decoupling) can be saved as blocks and re-applied when a schematic block with matching topology appears. This automates the expert's "copy the eval-board layout" habit.
- Datasheet layout sections can be converted (by an LLM) into per-IC structured constraints (loop membership, max distances, keepouts). These feed both placement objectives and semi-automatic critics, matching the per-IC review practice.

### Gaps
- No primary source was retrieved on how experts copy *eval-board* Gerbers/layouts (e.g., importing vendor reference designs), or on Altium "snippets"/"device sheets" or OrCAD reuse workflows.
- Release-version history of KiCad design blocks and multichannel was not verified.

---

## Q4. Consolidated, de-duplicated master layout-review checklist

### Takeaway
Merging five open checklists (azonenberg, grosdode, Pikafu, henrikh, jnoss) with vendor and review guidance (Altium, UWARG, VSE, Cadence, TI, ProtoExpress, MacroFab, bestpcbs, AllPCB, Flux) and KiCad's DRC catalogue gives ~190 distinct layout-review items. By primary tag, about 34% are pure geometry/DRC checks and about 43% need net/part semantics (roles such as "decap of U3 pin 7", "SW node", "diff pair") but are then computable. The remaining ~23% need judgment, external data (enclosure, datasheet prose) or simulation. Of the 28 Critical items, 24 are at least semi-automatable. *Severity and automation tags are my assignments, based on the sources' stated rationale.*

### Cited Findings

**Source checklists used (primary, read in full unless noted)**
- **[AZ]** Andrew Zonenberg, *pcb-checklist* (layout: 72 items; schematic: 60 items; BSD-3). "Nearly every line item here came from the school of hard knocks" — [layout-checklist.md](https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md); [repo](https://github.com/azonenberg/pcb-checklist). Forks such as [jaydcarlson/pcb-checklist](https://github.com/jaydcarlson/pcb-checklist) are older snapshots (missing the FPC, SMA-stitching and enclosure-bend items).
- **[GD]** grosdode, *PCB-design* checklist (schematic, layout, panels, assembly, bring-up; assembly section influenced by the Pick Place Podcast) — [pcb_checklist.md](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md).
- **[PK]** Pikafu, *pcb_design* best practices + board review checklists + fab/assembly drawing checklists — [README](https://github.com/Pikafu/pcb_design).
- **[HH]** Henrik Enggaard Hansen, electronics & electrical design checklist (pcbchecklist.com source) — [henrikh/pcb-checklist](https://github.com/henrikh/pcb-checklist).
- **[JN]** jnoss, pre-fab PCB checklist (sources include aqdi.com, a Fermilab assemblies checklist and EE.SE) — [jnoss/pcb-checklist](https://github.com/jnoss/pcb-checklist).
- **[KD]** KiCad DRC violation catalogue and custom-rule constraints — [pcbnew_inspecting.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_inspecting.adoc); [pcbnew_advanced.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc).
- **[AL]** Altium (Mark Harris) PCB design & review checklist: ≥3 board-level fiducials (two diagonally opposed) plus local fiducials at extremely fine-pitch parts; mounting clearance for washer and screw head; accurate 3D models; stackup/copper thickness confirmed with the fab; at least one continuous unbroken ground plane — [Altium checklist](https://resources.altium.com/p/pcb-design-and-review-checklist) (search summary; ground-plane item seen only in non-English versions). **[AL3]** DRC can pass electrically/functionally wrong designs; keep a functional requirements list — [Altium perils of design review](https://resources.altium.com/p/how-to-navigate-the-perils-of-pcb-design-review). Also [Altium layout review checklist](https://resources.altium.com/p/pcb-design-review-checklist-gets-you-manufacturing-quickly): some points are DRC-checkable, others manual.
- **[UW]** UWARG: review each IC circuit against its datasheet; for DFM, just confirm the rules match the fab's published capabilities and DRC is clean — [UWARG](https://uwarg-docs.atlassian.net/wiki/spaces/EL/pages/2173501609) (search summary).
- **[VSE]** Staged reviews and placement checklist (connectors vs enclosure, high-speed and sensitive parts, power parts, decoupling) — [VSE](https://www.vse.com/blog/a-pcb-layout-checklist-for-error-free-manufacturing/) (search summary).
- **[CD]** Cadence: clearance for IC extraction tools and sockets; electrical isolation of mounting holes; analog and digital commons joined at a single point — [Cadence placement risk/benefit](https://resources.pcb.cadence.com/blog/2023-pcb-design-and-risk-benefit-analysis-in-component-placement) (search summary).
- **[TI]** Switcher layout rules — [TPS61178](https://ti.com/document-viewer/TPS61178/datasheet/layout-guidelines-slvsda71918), [TPS55330](https://www.ti.com/document-viewer/TPS55330/datasheet/layout-guidelines-slvsbx81345), [SLVAFJ3](https://www.ti.com/document-viewer/lit/html/SLVAFJ3/GUID-90181CF4-7939-4962-A565-7204ECA6A0CF), [TPS62679 layout](https://www.ti.com/document-viewer/TPS62679/datasheet/layout) (search summaries).
- **[PE]** ProtoExpress DFA checklist: mask openings for exposed/thermal pads; test probes near component legs, with minimum test-point-to-component distance estimated from component height; silkscreen-to-mask spacing (4.5 mil cited) — [ProtoExpress DFA](https://www.protoexpress.com/blog/pcb-design-for-assembly-checklist-important-checks-for-layout-engineers/) (search summary).
- **[MF]** MacroFab: run your contract manufacturer's DRC continuously during layout; check silkscreen accuracy and revisions — [MacroFab](https://macrofab.com/blog/five-tips-to-clean-up-your-layout/) (search summary).
- **[BP]** DFM review areas (min trace/space, via drill, annular ring, hole-to-copper, copper-to-edge, mask dams, copper balance). Run DFM review before quote, before prototype release, before production release and after any material/layer/density/assembly change — [bestpcbs DFM checklist](https://www.bestpcbs.com/blog/2026/07/pcb-design-for-manufacturability-checklist/) (search summary).
- **[AP]** AllPCB: 4–5 mil minimum trace/space typical for prototypes; annular ring >3 mil — [AllPCB checklist](https://www.allpcb.com/allelectrohub/the-ultimate-checklist-for-error-free-pcb-prototyping-from-schematic-to-fabrication) (search summary; fab-specific).
- **[FX]** Flux: reference IPC-2221C for spacing and state the IPC-6012F revision/class for fabrication; staged schematic/layout/DFM reviews — [Flux review process](https://www.flux.ai/p/blog/pcb-design-review-process) (search summary).
- **[CE]** claude-eda (LLM skill prior art): placement priorities and numeric thresholds (crystal ≤5 mm from MCU, decap <3 mm from IC pin, USB ESD ≤10 mm from connector, antenna-to-matching ≤5 mm, mounting hole to component ≥2 mm) — [PLACEMENT-STRATEGY.md](https://github.com/l3wi/claude-eda/blob/main/templates/claude/skills/eda-pcb/reference/PLACEMENT-STRATEGY.md). *These thresholds are not sourced; treat them as defaults to be overridden by datasheets.*
- Other checklists referenced but not retrievable: a 40+-item KiCad-forum review checklist ([KiCad forum](https://forum.kicad.info/t/pcb-design-review-checklist-before-fabrication/67579)); Voler Systems and IBEX checklists linked from [henrikh](https://github.com/henrikh/pcb-checklist); Zuken CR-8000 "Circuit DR Navi", a commercial knowledge base that turns guidelines into structured review checklists ([Zuken](https://www.zuken.com/en/resource/datasheet-cr-8000-circuit-dr-navi/)).

**Legend.** Severity: **C** = critical (dead or unsafe board, unmanufacturable/unassemblable → respin); **M** = major (SI/PI/EMC/thermal/yield/reliability risk, possible respin); **m** = minor (debug convenience, documentation, cosmetics). Automation: **A** = geometry/DRC only (KiCad built-in DRC or custom rule named where applicable); **S** = semi-automatic (needs net classes, part roles or datasheet parameters, then computable); **J** = judgment / external info / simulation.

Source keys (all URLs above): AZ, GD, PK, HH, JN, KD, AL, AL3, UW, VSE, CD, TI, PE, MF, BP, AP, FX, CE, plus FD = Feranec ([forum](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629), [tip 095](https://courses.fedevel.com/blog/tip-095-you-may-want-to-place-all-the-components-on-the-board-before-you-start-doing-layout), [tip 038](https://courses.fedevel.com/blog/tip-038-place-fiducials-in-the-pcb-corners-and-on-the-side-where-smd-components-are-fitted)), HT = Hartley ([ProtoExpress](https://www.protoexpress.com/blog/rick-hartley-pcb-design-recommendations-to-minimize-emi/), [Altium](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley), [EEJ](https://eejournal.com/article/matters-of-integrity)), BD = [Beyond Design HS rules](https://iconnect007.com/article/143099/beyond-design-highspeed-rules-of-thumb/143096/design), AD = [Autodesk placement](https://www.autodesk.com/products/eagle/blog/pcb-layout-basics-component-placement/), KG = [KiCad Getting Started](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/getting_started_in_kicad/getting_started_in_kicad.adoc), KF = [KiCad forum placement thread](https://forum.kicad.info/t/strategy-to-use-for-placing-components/23682), MIT = [MIT handout](https://mitocw.ups.edu.ec/courses/mechanical-engineering/2-996-biomedical-devices-design-laboratory-fall-2007/labs/lab_handout3.pdf), NX = [NextPCB](https://www.nextpcb.com/blog/how-many-layers-can-a-pcb-have), PS = [ProtoExpress stackup guide](https://www.protoexpress.com/pcb-design-guides/pcb-stack-up-design-guide/), JL = [JLCPCB stackup](https://jlcpcb.com/blog/multilayer-pcb-stackup), JR = [JLCPCB routing rules](https://jlcpcb.com/blog/pcb-routing-rules-best-practices), JP = [JLCPCB placement guide](https://jlcpcb.com/blog/pcb-component-placement-guide-2026), EN = [electronics-notes](https://www.electronics-notes.com/articles/analogue_circuits/pcb-design/pcb-layout-routing.php), PC = [PCD&F 2019](https://www.qgdigitalpublishing.com/article/PCB+Guided+Insights/3388181/589425/article.html), FXM = [Flux mistakes](https://www.flux.ai/p/blog/pcb-design-mistakes), FXG = [Flux grounding](https://www.flux.ai/p/blog/pcb-grounding-techniques), FXP = [Flux placement](https://docs.flux.ai/tutorials/component-placement), BG = [bestpcbs ground plane](https://www.bestpcbs.com/blog/2026/09/circuit-board-ground-plane-layout/), ICD = [ICD 2012](https://www.icd.com.au/articles/Interactive_Place_&_Route_PCBDesign-Dec2012.pdf), WAT = [UW Rocketry](https://uwaterloo.atlassian.net/wiki/spaces/ROCKETRY/pages/43024155641/Design+Reviews).

#### Master checklist table

| ID | Category | What to check | Why | Sev | Auto | Sources |
|---|---|---|---|---|---|---|
| PRC-01 | Process | Schematic review signed off before layout; pin/gate swaps made during layout back-annotated and re-reviewed | Laying out an unreviewed or out-of-sync schematic carries its errors into the board | C | S (parity auto; sign-off J) | AZ, VSE |
| PRC-02 | Process | Board/schematic parity: no missing, extra or duplicate footprints; pad nets match schematic; footprint attributes match symbol | "LVS": confirms the layout implements the schematic | C | A (DRC: Missing/Extra/Duplicate footprint, Pad net doesn't match schematic, Footprint attributes don't match symbol) | HH, JN, KD |
| PRC-03 | Process | Zero unrouted connections / airwires; no polygon breaks | Open nets | C | A (DRC: Missing connection between items) | HH, JN, KD |
| PRC-04 | Process | DRC 100% clean; every excluded/waived violation inspected and signed off | Waivers hide real defects | C | A (+J for waivers) | AZ, GD, KD |
| PRC-05 | Process | Rules (track/space, drill, annular ring, mask web, silk width, edge clearance) set from target fab/assembler capability *before* layout and kept current | DRC is only meaningful if the rules equal fab limits; reviewers then just confirm rules + clean DRC | C | S (setting) → A (checking) | GD, PK, UW, MF |
| PRC-06 | Process | Layout reviewed manually against a functional requirements list | DRC passes many functionally wrong designs | M | J | AL3 |
| PRC-07 | Process | Each significant IC circuit (regulators, LDOs, MCUs, transceivers) reviewed against its datasheet layout guidelines, ideally by a separate reviewer per IC | IC-specific constraints live in datasheets | M | J (LLM extraction can make it S) | UW, JN, WAT |
| PRC-08 | Process | Staged reviews held: pre-layout constraints, placement review, critical-routing review, final/DFM | Errors are cheaper to fix early; each review isolates one error class | M | J | VSE, FX |
| PRC-09 | Process | Review tied to a specific version-controlled revision; design decisions documented | Avoids reviewing stale files | m | J | WAT, HH |
| PRC-10 | Process | Every part available in the chosen package; no NRND/obsolete parts at layout freeze | A late package change forces re-layout | M | S | AZ, GD |
| DFM-01 | DFM | Features don't push fab limits unnecessarily (wider traces, larger vias where space allows) | Yield, cost ("just because your manufacturer can process 3 mil traces...") | M | A (margin-to-limit report) | AZ, GD, AP |
| DFM-02 | DFM | Annular ring ≥ fab/IPC-class minimum (PK: 5 mil Class 2, 7 mil Class 3 for 10 mil vias; AP: >3 mil) | Drill wander breaks out of the pad | C | A (annular_width) | PK, AP, KD |
| DFM-03 | DFM | Hole-to-hole and hole-to-copper clearances | Breakout, shorts | C | A (hole_clearance, hole_to_hole) | KD, BP |
| DFM-04 | DFM | Copper-to-edge clearance (unless edge plating/edge-launch confirmed with fab) | Exposed copper, router wear, shorts to chassis | M | A (edge_clearance) | GD, AZ, KD, BP |
| DFM-05 | DFM | Via aspect ratio and microvia stack rules within fab capability | Plating reliability | M | A (microvia_aspect_ratio, microvia_stack_depth) | PK, KD |
| DFM-06 | DFM | Few unique via/drill types | Faster, cheaper fab | m | A | PK |
| DFM-07 | DFM | Mask dams between fine-pitch pads; no mask aperture bridging different nets | Solder bridges | M | A (bridged_mask) | BP, KD |
| DFM-08 | DFM | No copper slivers; no too-narrow copper necks | Slivers flake; necks fuse | m | A (Copper sliver; connection_width) | KD |
| DFM-09 | DFM | Copper balanced per layer; stackup symmetric | Warpage | m | S | BP, PS |
| DFM-10 | DFM | Outline closed and valid; internal corners millable; external corners rounded | Unmillable shapes; sharp edges | M | A (Board has malformed outline) | HH, KD, PK |
| DFM-11 | DFM | PTH finished hole ≥ lead + ~0.2 mm (≥10 mil); square pins sized by diagonal; plating allowance; pad ≥ hole + 10–15 mil | Parts won't insert; weak joints | C | S (needs lead dimensions) | GD, JN, HH |
| DFM-12 | DFM | Via tenting/plugging policy decided and consistent; untented vias kept off/away from pads | Solder theft vs test access | m | A | GD, JN |
| DFM-13 | DFM | Surface finish specified (e.g. ENIG for flatness/fine pitch) | Solderability, coplanarity | M | J | AZ, PK |
| DFM-14 | DFM | Board size fits standard panels efficiently | Cost | m | J | PK |
| DFM-15 | DFM | Margins chosen for production volume, not just prototypes ("10–50 boards doesn't mean 1000") | Tolerance stack-up at volume | M | J | GD |
| STK-01 | Stackup | Stackup (materials, dielectric thicknesses, copper weights, finished thickness) verified with the fab and written in fab notes | Impedance and manufacturability depend on the fab's real materials | C | J | AZ, AL, FD, HT |
| STK-02 | Stackup | Every signal layer one dielectric from a solid reference plane; no unshielded adjacent signal layers | Field containment, return path, crosstalk | M | S (needs layer roles) | HT, PK, PS, JL |
| STK-03 | Stackup | Controlled-impedance nets, targets and reference layers listed in fab notes | Fab tunes widths to hit Z | M | S | AZ, PK |
| STK-04 | Stackup | Impedance calcs include solder mask (or mask removed over RF lines) | Mask shifts Z and adds loss | M | S | AZ, PK |
| STK-05 | Stackup | Controlled-impedance traces use the computed width/gap for their layer (per-layer net-class rules) | Mismatch causes reflections | M | A (once net classes defined) | PK, HH |
| STK-06 | Stackup | Layer count is the minimum giving continuous references, power copper and escape; +2 layers if channel use >70% | Cost vs SI/routability | M | J (S estimate) | NX, VSE, JL |
| STK-07 | Stackup | Sequential lamination cycles limited (≤4) | Yield, cost | m | S | PS |
| MEC-01 | Mechanical | Outline, dimensions and mounting holes match the enclosure/card rack (checked in 3D with accurate models) | Board doesn't fit | C | S (needs MCAD/enclosure) | AZ, AL, CE |
| MEC-02 | Mechanical | Mounting holes have clearance/keepout for screw head and washer | Shorts to fastener; crushed parts | M | A (keepout/rule area) | AZ, AL, HH |
| MEC-03 | Mechanical | Mounting holes deliberately plated+grounded (with stitching) or isolated | EMC/safety; free GND test points | M | S | AZ, PK, HH, CD |
| MEC-04 | Mechanical | Off-board connectors match the mating standard: orientation, keying, pin 1, FPC top/bottom contact | Mis-mating, mirrored pinout | C | J | AZ, JN |
| MEC-05 | Mechanical | Clearance for mating plug/cable and finger access to latches (mating connector modeled in 3D) | Can't plug/unplug | M | S (3D) | AZ, GD |
| MEC-06 | Mechanical | UI elements (LEDs, buttons, switches) on the outward-facing side, logically arranged and oriented | Usability | M | J | AZ, HH |
| MEC-07 | Mechanical | Component heights within enclosure; heatsink/fan clearance | Collisions | M | S (3D) | AZ, HH |
| MEC-08 | Mechanical | No part collisions or courtyard overlaps | Can't be assembled | C | A (Courtyards overlap) | AZ, KG, KD |
| MEC-09 | Mechanical | Perimeter keepouts (card guides, conveyor/handling border ~3 mm, mouse bites) respected | Handling and depaneling | M | A (rule area) | AZ, GD |
| MEC-10 | Mechanical | MLCCs/stress-sensitive parts away from V-scores, mouse bites and mounting holes, oriented against flex; soft-termination for >1210 | Cracked caps → shorts | M | S | AZ, PK |
| MEC-11 | Mechanical | Connectors mechanically anchored (THT posts/hybrid), especially RF and frequently mated ones | Pad lift-off | M | J | PK, GD |
| MEC-12 | Mechanical | Edge/right-angle connectors at the edge with correct overhang; edge fingers per spec | Fit | M | S | GD, HH |
| MEC-13 | Mechanical | Tool access: IC extraction, sockets, programming fixtures, screwdrivers, probes | Serviceability | m | S | HH, CD |
| MEC-14 | Mechanical | Connectors/mounting holes on a coarse grid; round board dimensions | MCAD integration, drawings | m | A | GD |
| PLC-01 | Placement | Order: fixed parts → main ICs (CPU/memory) → other ICs → power → small passives | Fixed items constrain everything else | M | J (process) | FD, GD, JP, CE |
| PLC-02 | Placement | Parts grouped by functional block; power, analog, digital and RF regions separated | Short routes; contained noise | M | S (sheet/role) | FXP, GD, KG |
| PLC-03 | Placement | Switching converters physically away from sensitive analog | Noise coupling | M | S | GD, AZ |
| PLC-04 | Placement | Temperature-sensitive parts (electrolytics, oscillators, references) away from hot parts | Lifetime, drift | M | S | HH, JN |
| PLC-05 | Placement | Interface ICs, ESD and filters next to their connectors | Short exposed path; protection works | M | S | HH, CE |
| PLC-06 | Placement | Series/damping resistors at the source; terminations at the load | Termination only works at the correct end | M | S | HH, JN |
| PLC-07 | Placement | Crystal/oscillator adjacent to its IC; short traces; ground guard | Jitter, EMI, start-up | M | S (CE default ≤5 mm) | HH, JN, CE |
| PLC-08 | Placement | ADC anti-alias filters close to the ADC input | Pickup after the filter | M | S | GD, HH |
| PLC-09 | Placement | All components placed before routing starts | Inserting parts into routed areas is very hard | M | J (process) | FD, MIT |
| PLC-10 | Placement | Ratsnest length and crossings minimized | Routability proxy | M | A | AD, KG, KF |
| PLC-11 | Placement | Routability trial (quick autoroute ≥~85% completion) before committing | Exposes placement problems early | M | A | AD |
| PLC-12 | Placement | Routing channels left between dense ICs (memories, BGAs) | Escape room | M | S | FD |
| PLC-13 | Placement | Rework: any part replaceable without removing others; tweezer/iron access | Repairability | m | S | JN, GD, ICD |
| PLC-14 | Placement | No routing under noisy/sensitive parts; no vias under metal-film resistors | Coupling | m | S | HH, GD |
| PLC-15 | Placement | Polarized/like parts in one orientation or a repeatable pattern | Human/AOI inspection | m | A | GD, JN, HH |
| PLC-16 | Placement | Footprints on a regular placement grid (origin on grid) | Neatness, MCAD | m | A | GD, PK |
| PLC-17 | Placement | Tall parts don't shadow small parts from AOI; SMD ≥2–5 mm from THT joints if selective soldering | Inspection/soldering | m | S | GD |
| PLC-18 | Placement | Nearby inductors oriented/spaced to limit magnetic coupling | Crosstalk | m | S | CE (unsourced) |
| PLC-19 | Placement | Heat sources placed for airflow/edge; copper available for spreading | Thermal | M | S | CE, JN |
| PDN-01 | Power integrity | Decoupling caps as close as possible to power pins; each power pin has its own cap | Loop inductance | M (C for fast ICs) | S (cap↔pin association; CE default <3 mm) | AZ, JN, KG, CE |
| PDN-02 | Power integrity | Smallest-value cap closest to the pin | HF effectiveness | M | S | PK, TI |
| PDN-03 | Power integrity | Low-inductance cap mounting (via-in-pad if available, else short side vias straight to plane) | Mounting inductance dominates | M | S | AZ, HH |
| PDN-04 | Power integrity | Bulk capacitance at power entry and regulator outputs | LF stability | M | S | HH, CE |
| PDN-05 | Power integrity | Every IC power/ground pin actually connected (pour/thermal connections on all layers) | Floating supply pins | C | A (parity + connectivity) | GD, HH |
| PDN-06 | Power integrity | Trace/plane width sized for current and temperature rise | Burn-out, IR drop | C | S (needs per-net current) | AZ, HH, JN, GD |
| PDN-07 | Power integrity | Vias sized and multiplied on high-current paths | Via fusing, IR drop | M | S | GD, HH |
| PDN-08 | Power integrity | Plane slots from via antipads minimized | Slotted planes break PDN and returns | M | S | AZ |
| PDN-09 | Power integrity | Power filtered where it enters the board | Conducted noise | M | S | GD |
| PDN-10 | Power integrity | DNP footprints for extra input/output caps on regulators | Bring-up tuning | m | J | PK |
| PWR-01 | Power conversion | Switching hot loop (e.g. input cap–switch–rectifier; boost: switch–rectifier–output cap) has minimal area | High di/dt loop radiates and rings | C | S (topology roles) + J/sim | TI, GD |
| PWR-02 | Power conversion | SW-node copper area minimal; ground plane under the regulator | dV/dt antenna | M | S | TI |
| PWR-03 | Power conversion | FB network next to FB pin; FB trace routed away from SW/inductor | Regulation noise | M | S | TI |
| PWR-04 | Power conversion | Current-sense lines Kelvin-routed apart from power planes; gate-drive return routed with its gate | Accuracy, ringing | M | S | TI |
| PWR-05 | Power conversion | AGND/PGND separated and joined as the datasheet specifies | Ground noise into the controller | M | S/J | TI |
| PWR-06 | Power conversion | Tracks between switch, inductor and caps (including GND) short and wide | Loss, EMI | M | S | GD |
| PWR-07 | Power conversion | Connectors and regulators current-rated in the chosen package | Overheating | C | J | AZ |
| GND-01 | Ground/return | At least one continuous, unbroken ground plane | Return path, EMI | M | S | AL |
| GND-02 | Ground/return | High-speed nets don't cross plane splits, slots or voids; if unavoidable, stitching caps/vias | Detoured return acts as an antenna | C (HS) | S (trace vs reference-plane geometry) | AZ, HH, HT, BD |
| GND-03 | Ground/return | Return/stitching vias next to signal vias where a signal changes reference layers | Return continuity | M | S | PK, BD, BG |
| GND-04 | Ground/return | Ground planes not split without justification (precision/audio <~100 kHz is the noted exception) | Splits usually worsen EMI | M | J | GD, HT, FXG |
| GND-05 | Ground/return | If analog/digital grounds are separated, they join at exactly one point | Ground loops | M | S | HH, JN, CD |
| GND-06 | Ground/return | No plane bottlenecks or isolated islands | Starved returns; antennas | M | A (Isolated copper fill) | GD, JN, KD |
| GND-07 | Ground/return | Vias spread evenly across planes (no via "walls" that slot the plane) | Avoid slots | m | S | JN |
| GND-08 | Ground/return | No signals along board edges; consider an edge ground ring/stitching | Edge radiation | m | A | HH, GD |
| GND-09 | Ground/return | Current return path checked for every critical net | Root cause of many SI/EMI problems | M | S/J | GD, HT |
| HS-01 | High-speed | Diff pairs routed coupled at impedance gap; uncoupled length limited | Mode conversion, Z | C | A (diff_pair_gap, diff_pair_uncoupled) | AZ, HH, KD |
| HS-02 | High-speed | Intra-pair skew matched | Mode conversion | M | A (skew) | AZ, JN, KD |
| HS-03 | High-speed | Inter-signal length matching per interface budget (e.g. DDR) | Timing | M | A (length/skew rules) | AZ, JR |
| HS-04 | High-speed | Clearance to aggressors; diff pairs clear of non-coupled nets | Crosstalk | M | S | AZ, GD |
| HS-05 | High-speed | Stubs and layer changes minimized on HS nets | Reflections | M | A/S (via_count) | HH, AZ, KD |
| HS-06 | High-speed | Terminations present and at the correct end | Reflections | M | S | HH, JN |
| HS-07 | High-speed | Mitered or curved (r > 3W) bends on impedance-sensitive traces | Discontinuity (minor) | m | A (track_angle) | HH, JN |
| HS-08 | High-speed | Wide connector pads compensated (plane cut-outs under pads) | Impedance dip | M | J/sim | AZ |
| HS-09 | High-speed | Footprint option for a common-mode filter on off-board HS pairs | EMC fallback | m | J | HH |
| HS-10 | High-speed | Series-R / 0 Ω placeholders on fast single-ended lines | Edge-rate control later | m | J | HH, PK |
| HS-11 | High-speed | Critical nets (clocks, pairs, sensitive analog, switching loops) routed before bulk nets | Everything else routes around them | M | J (process) | JR, EN, PC |
| HS-12 | High-speed | "Low-frequency" buses judged by edge rate/harmonics, not clock rate | Fast edges radiate | m | J | GD |
| RF-01 | RF | RF line (e.g. GCPW) impedance verified with the real stackup; mask effect accounted for | Mismatch | M | S | AZ, PK |
| RF-02 | RF | Via-fence pitch ≤ λ/8 along GCPW/stripline | Leakage/parasitic modes | M | S (needs frequency) | PK, HH |
| RF-03 | RF | Stitching vias in large top-layer ground pads (e.g. SMA) | Resonances | M | S | AZ |
| RF-04 | RF | Antenna/module keep-outs and ground clearance per datasheet | Detuning | C | A once keepout drawn; S to derive | GD, JN, CE |
| RF-05 | RF | Shield-can footprint option over RF/sensitive circuits | EMC fallback | m | J | HH |
| RF-06 | RF | Edge-launch connector: fab confirmed for copper to edge | Launch performance | M | J | AZ |
| ANA-01 | Analog | Guard rings/EMI cages on sensitive analog nodes where needed | Leakage, pickup | M | J | AZ |
| ANA-02 | Analog | Sensitive analog physically separated from SMPS/noisy digital | Noise | M | S | AZ, GD, KG |
| ANA-03 | Analog | Noisy traces not adjacent to critical traces on any layer (including layer-to-layer) | Crosstalk | M | S | GD |
| ANA-04 | Analog | MLCC microphonics considered near acoustic sources | Noise | m | J | AZ |
| EMC-01 | EMC/ESD | ESD/TVS parts at the connector entry with a short, direct ground path | Shunt the surge before it spreads | M | S | HH, CE |
| EMC-02 | EMC/ESD | No small or sharp floating copper that can act as an antenna | Radiation | m | A (Isolated copper fill) | JN, KD |
| EMC-03 | EMC/ESD | Ferrite beads have DC-current margin; filter target frequencies defined | Bead impedance collapses under bias | m | J | HH |
| EMC-04 | EMC/ESD | Footprint option for SMPS RC snubbers | Ringing | m | J | HH |
| EMC-05 | EMC/ESD | Plane keepouts and chassis bonding for shielded connectors and magnetics | Isolation, EMC | M | S | AZ, HH |
| THM-01 | Thermal | Thermal reliefs on plane connections for solderability (except intended heat-sinking pads) | Cold joints | M | A (zone_connection) | AZ, GD, PK, JN |
| THM-02 | Thermal | Solid connections plus thermal-via arrays under heat-dissipating pads; copper on several layers | Junction temperature | M | S | AZ, JN, HH |
| THM-03 | Thermal | Thermal balance on 2-terminal chips; correct pad spacing for 0402/0201 | Tombstoning | M | S | AZ, GD |
| THM-04 | Thermal | Thermal lands left unmasked; exposed pads tied to the correct net (not always GND) | Heat transfer; function | M | S | JN, HH |
| THM-05 | Thermal | Thermal-relief spokes fully resolved (no starved thermals) | Weak connection | M | A (Thermal relief connection incomplete; min_resolved_spokes) | KD |
| FP-01 | Footprints | Footprint matches the actual ordered package (e.g. not 0805 for an 0603); symbol pinout matches package | Unassemblable or wrong pins | C | S | AZ, FXM |
| FP-02 | Footprints | Pinout drawings read in the correct view (top vs bottom) | Mirrored pinout | C | J | AZ, HH |
| FP-03 | Footprints | 1:1 printout checked against physical parts | Catches dimension errors | M | J | AZ, GD, JN |
| FP-04 | Footprints | 3D models present and verified against footprints | Valid MCAD checks | M | S | AZ, AL |
| FP-05 | Footprints | Mask apertures on all SMT lands and PTH pads | Unsolderable pads | C | A | AZ |
| FP-06 | Footprints | SMD vs NSMD pad definition confirmed (especially BGA) | Joint reliability | M | S | AZ, GD |
| FP-07 | Footprints | New/vendor footprints checked against datasheet land patterns | Vendor libraries are often wrong | M | J | JN, HH, FXM |
| FP-08 | Footprints | Courtyard present and valid; footprint matches library copy and symbol filters | Overlap checks depend on courtyards | m | A (no/malformed courtyard; doesn't match library/filters) | KD |
| FP-09 | Footprints | No vias embedded in footprints | Blocks via consolidation | m | A | PK |
| FP-10 | Footprints | Exposed/thermal pads present; assembly note when the pad is the only GND connection | Function | M | S | HH |
| FP-11 | Footprints | SMT pad length ≥ lead + ~8 mil (4 mil per side) | Solder fillet | M | S | JN |
| RTE-01 | Routing | No acute trace–pad or trace–trace angles | Acid traps | m | A (track_angle) | HH, KD |
| RTE-02 | Routing | Adjacent IC pins never bridged directly; traces leave pad ends (U-shape) | Looks like a short at inspection; bridging | m | A/S | GD, HH, JN |
| RTE-03 | Routing | No dangling tracks or vias ("traces that lead to nowhere") | Stubs, confusion | m | A (Track has unconnected end; via_dangling) | GD, KD |
| RTE-04 | Routing | Traces kept off the board outline and depanel zones | Damage | m | A (edge_clearance) | GD |
| RTE-05 | Routing | Superfluous vias removed | Reliability, cost | m | A | HH |
| RTE-06 | Routing | Teardrops where mechanical stress is expected | Cracks | m | A | AZ |
| RTE-07 | Routing | Unconstrained traces generously wide (avoid using minimum widths everywhere) | Yield, low impedance | m | A | GD |
| ZON-01 | Zones | Zones refilled after the last edit and before CAM; pours actually enabled | Stale fills cause shorts/opens | C | A | AZ, GD |
| ZON-02 | Zones | No pour between adjacent IC pins (keep-out between pins) | Inspection confusion, bridging | m | S | HH |
| ZON-03 | Zones | Overlapping zones have correct priorities; no unintended intersections | Unexpected shorts/voids | M | A (Copper zones intersect) | KD |
| PST-01 | Paste/mask | No untented/unfilled vias in pads (except low-power QFN where voiding is acceptable) | Solder wicking, voids | C | A | AZ, GD |
| PST-02 | Paste/mask | Paste windows on large exposed pads segmented (~70% area unless datasheet says otherwise) | Float, voids, squeegee scoop | M | A (solder_paste_rel_margin) | AZ, PK, GD |
| PST-03 | Paste/mask | Small pads 100% aperture; large pads reduced | Solder volume | m | A | AZ |
| PST-04 | Paste/mask | No paste on edge fingers, test points, fiducials or DNP parts | Contamination | M | A/S | AZ, GD |
| PST-05 | Paste/mask | Mask clearance around pads (~50 µm typical) | Mask on pad / bridging | m | A (solder_mask_expansion) | AZ |
| ASM-01 | Assembly | Fiducials: ≥3 global (asymmetric to catch rotation/flip), on both sides if double-sided, local fiducials at fine pitch, copper/mask clearance kept | Machine-vision alignment | M | A/S | AZ, AL, GD, FD |
| ASM-02 | Assembly | Pin-1/polarity marks visible after assembly | Orientation errors | M | S | GD, JN, HH |
| ASM-03 | Assembly | BOM and pick-and-place consistent with the board (including DNP) | Assembly errors | M | S | GD |
| ASM-04 | Assembly | No unnecessarily tiny parts (the smallest part sets stencil thickness) | Yield, hand soldering | m | J | GD |
| ASM-05 | Assembly | Plastic connectors rated for reflow | Melting | m | J | GD |
| ASM-06 | Assembly | Layer-number markers in copper | Layer-order errors | m | A | AZ |
| ASM-07 | Assembly | Assembly order feasible (mounting one part doesn't block another) | Buildability | m | J | HH |
| ASM-08 | Assembly | Footprint accepts alternate packages where possible | Supply chain | m | J | GD |
| DFT-01 | Test/debug | Test points on power rails and critical signals; hidden nets made probe-accessible | Bring-up | M | S | GD, HH, PK |
| DFT-02 | Test/debug | GND test/hook points next to critical test points | Short probe ground loops | m | S | GD, HH, PK |
| DFT-03 | Test/debug | Probe clearance around test points; test pads away from the edge (JN: not within 5 mm) | Fixture access | m | A | AZ, JN |
| DFT-04 | Test/debug | Programming/debug headers, jumpers and reset accessible | Development | M | J | GD, HH, JN |
| DFT-05 | Test/debug | Status LEDs present | Debug | m | J | JN, PK |
| DFT-06 | Test/debug | Software-readable board-revision straps | Field support | m | J | HH |
| DFT-07 | Test/debug | 0 Ω links to isolate sections/measure current; DNP pull options | Staged bring-up | m | J | GD, PK |
| DFT-08 | Test/debug | Caps oriented with power nets facing the same way | Avoid shorts while probing | m | S | PK |
| DFT-09 | Test/debug | Test-probe to component spacing set from component height | Probe access | m | S | PE |
| SLK-01 | Silkscreen | No silk on pads, drills or exposed copper; silk clipped by mask flagged | Contaminates joints | M | A (silk_clearance; Silkscreen clipped by solder mask) | AZ, GD, JN, KD |
| SLK-02 | Silkscreen | Text height/thickness within fab limits and legible (PK: ≥0.1") | Illegible | m | A (text_height, text_thickness) | AZ, KD, PK |
| SLK-03 | Silkscreen | Text reads from at most 2 directions; consistent orientation | Readability | m | A | HH, JN, GD |
| SLK-04 | Silkscreen | Bottom-side text mirrored | Readability | m | A (Mirrored/Non-mirrored text checks) | AZ, KD |
| SLK-05 | Silkscreen | Revision, date, name/logo; blank box for serial/assembly revision | Traceability | m | S | AZ, HH, JN, GD |
| SLK-06 | Silkscreen | Labels for connector pinouts, test points, LEDs, switches, jumpers, fuse rating, functional groups | Usability, debug | m | S | HH, JN, AZ |
| SLK-07 | Silkscreen | Tick marks every 5/10 pins; corner pins numbered on high-pin-count ICs/connectors | Probing | m | S | HH, JN |
| SLK-08 | Silkscreen | Silk removed (not crammed) in dense areas | Ambiguous labels | m | J | AZ |
| SLK-09 | Silkscreen | Reference designators annotated geographically (left→right, top→bottom) | Find parts quickly | m | A | HH, JN |
| SLK-10 | Silkscreen | Connector overhang beyond the board edge marked on silk | Assembly | m | S | GD |
| HV-01 | HV/safety | Creepage and clearance sized for voltage, including between layers | Arcing, safety | C | A (creepage, clearance by net class) | GD, HH, KD |
| HV-02 | HV/safety | Isolation barriers (slots, keepouts) adequately sized | Safety | C | S | HH |
| HV-03 | HV/safety | Signal and power not in the same connector; connectors for different purposes not interchangeable | Mis-mating fire (Fermilab 1987 example) | M | J | HH |
| CAM-01 | Outputs | DRC and zone fill re-run immediately before export | Stale outputs | C | A | AZ |
| CAM-02 | Outputs | Gerbers and drill exported together and inspected in an independent viewer | Misalignment, missing layers | M | S/J | AZ, PK |
| CAM-03 | Outputs | Uploaded files are the latest and complete (layer count, geometry exported correctly) | "Yes, this does happen" | C | S | HH |
| CAM-04 | Outputs | Fab drawing: dimensions, datums, drill table, stackup table, impedance callouts, IPC class, finish, mask/silk colors | Fab intent | M | J | PK, FX |
| CAM-05 | Outputs | Assembly drawing: paste type, staking for large parts, hole sizes | Assembly intent | m | J | PK |
| CAM-06 | Outputs | Gerber X2; drill format stated | Fewer CAM errors | m | A | GD |
| PNL-01 | Panel | Panelization specified (tabs vs V-score); rails ≥3 mm; panel stiffness | Handling | m | S | AZ, GD |
| PNL-02 | Panel | Panel-position markers for location-specific reflow issues | Process debug | m | A | AZ |
| PNL-03 | Panel | Tracks/parts clear of depanel zones | Damage | M | A | GD, AZ |
| FLX-01 | Flex | Flex components oriented to minimize bending forces | Cracking | M | S | AZ |
| FLX-02 | Flex | Teardrops on all wire-to-pad connections on flex | Cracks | M | A | AZ |

#### Coverage statistics (computed from the table above)
- Total distinct items: **190** across 24 categories: Process 10; DFM 15; Stackup 7; Mechanical 14; Placement 19; Power integrity 10; Power conversion 7; Ground/return 9; High-speed 12; RF 6; Analog 4; EMC/ESD 5; Thermal 5; Footprints 11; Routing 7; Zones 3; Paste/mask 5; Assembly 8; Test/debug 9; Silkscreen 10; HV/safety 3; Outputs 6; Panel 3; Flex 2.
- Severity: C = 28, M = 98, m = 64.
- Automation class (primary tag): A = 61, A/S = 4, S = 79, S/J = 3, J = 43 (A-dominant share ≈ 34%, S-dominant ≈ 43%, J ≈ 23%).
- Of the 28 Critical items: A = 14, A/S = 0, S = 10, S/J = 0, J = 4 — i.e. 86% of Critical items are at least semi-automatable.

### Inferences
- About 43% of items fall into the **semi-automatic (S)** class (79 S + 3 S/J of 190). For automation, the main enabler is a **semantic annotation layer** (part roles, net roles, currents, voltages, frequencies) more than better geometry code. KiCad already supplies much of the plumbing: net classes, component classes, custom rules with `A.NetClass`, `hasComponentClass()`, `inDiffPair()`, `intersectsCourtyard()`, `enclosedByArea()` and `fromTo()` ([KiCad custom rules](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc)).
- The sources' severity language ("school of hard knocks", "yes, this does happen") suggests Critical items cluster around **parity, footprints/pinouts, mechanical fit, stale outputs, current capacity and HV spacing**. These are mostly A/S-checkable, so a critic stack can catch most respin-class errors without needing an LLM's judgment.
- Many J items are "option" items (DNP snubbers, common-mode-filter footprints, shield cans). They are low-risk recommendations an LLM can raise as suggestions, not gates.

### Gaps
- The Sierra Circuits, Macrofab, JLC and PCBWay official DFM checklists and the ADI/TI formal "layout review checklist" documents could not be retrieved verbatim. Only search summaries were available.
- No NASA/JPL/aerospace layout review checklist was found. The closest documents are NASA-STD-8739 workmanship standards, which search results mentioned but which were not accessed.
- Oxide Computer, Antmicro, Adafruit and SparkFun published review checklists were not found (Antmicro publishes an open hardware portal of designs, not a checklist: [Antmicro open hardware portal](https://antmicro.com/blog/2023/04/open-hardware-portal)). "Ajay Bhargav's checklist" could not be located.

---

## Q5. Which layout mistakes most often cause respins, and is there frequency or severity data?

### Takeaway
No industry survey ranking layout-caused respins was found. The evidence is anecdotal: checklists explicitly built from past failures, and vendor "common mistakes" articles. Across those sources the recurring respin causes are footprint/pinout errors, decoupling misplacement, broken return paths/plane splits, mechanical misfit, unconnected nets, thermal neglect and stale/incorrect output files.

### Cited Findings
- Zonenberg's checklist is explicitly a failure log: "I made these mistakes so you don't have to! Nearly every line item here came from the school of hard knocks" — [azonenberg/pcb-checklist README](https://github.com/azonenberg/pcb-checklist).
- Footprint mismatches are "equally common". Example: "selecting an 0805 footprint for a 0603 physical part will lead to assembly failure and an immediate board revision." Vendor library parts are often less reliable than they appear. Floating logic nets "frequently escape initial routing checks." Poor placement is a root problem that affects routing, layer count and heat — [Flux: PCB design mistakes](https://www.flux.ai/p/blog/pcb-design-mistakes).
- First-board mistake: decoupling capacitors placed for tidiness rather than near the IC power pins — [Hubble: 10 common mistakes on your first custom PCB](https://hubble.com/community/guides/10-common-mistakes-on-your-first-custom-pcb/).
- Lists of common mistakes also appear at [AllPCB 7 common mistakes](https://www.allpcb.com/blog/pcb-knowledge/7-common-pcb-design-mistakes-and-how-to-avoid-them.html) and [Altair "10 common errors"](https://altair.com/resource/10-common-errors-to-avoid-in-electrical-board-design) (landing page only; contents not retrieved).
- Wrong production files: "Has the correct/latest files been uploaded? Yes, this does happen." Also, a misjoined connector at Fermilab (1987) drew several amps through 1 A-rated cables and started a fire — [henrikh checklist](https://github.com/henrikh/pcb-checklist).
- KiCad-specific failure mode: re-run DRC and zone fills before exporting CAM files, and export Gerber and drill together — [azonenberg layout checklist](https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md); "do not forget to turn [ground planes] on before generating the fabrication files" — [grosdode](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md).
- DRC can pass electrically or functionally incorrect designs — [Altium](https://resources.altium.com/p/how-to-navigate-the-perils-of-pcb-design-review).
- Return-path mismanagement is the root of ground bounce, power-path problems and EMI (Bogatin) — [EE Journal](https://eejournal.com/article/matters-of-integrity). Stackup is the most-often-wrong item (Hartley) — [Altium/Hartley](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley).

#### Consensus ranking (proxy, not frequency)
Number of independent sources (of the keys in the table) that flag each item. This measures agreement among checklist authors, **not** measured failure frequency. Top 25 by source count, then severity:

| Rank | ID | Item (abridged) | Sev | # sources | Sources |
|---|---|---|---|---|---|
| 1 | GND-02 | High-speed nets don't cross plane splits, slots or voids; if unavoidable, stitching caps/vias | C (HS) | 4 | AZ, HH, HT, BD |
| 2 | PDN-06 | Trace/plane width sized for current and temperature rise | C | 4 | AZ, HH, JN, GD |
| 3 | PRC-05 | Rules (track/space, drill, annular ring, mask web, silk width, edge clearance) set from target fab/assemble... | C | 4 | GD, PK, UW, MF |
| 4 | STK-01 | Stackup (materials, dielectric thicknesses, copper weights, finished thickness) verified with the fab and w... | C | 4 | AZ, AL, FD, HT |
| 5 | ASM-01 | Fiducials: ≥3 global (asymmetric to catch rotation/flip), on both sides if double-sided, local fiducials at... | M | 4 | AZ, AL, GD, FD |
| 6 | DFM-04 | Copper-to-edge clearance (unless edge plating/edge-launch confirmed with fab) | M | 4 | GD, AZ, KD, BP |
| 7 | MEC-03 | Mounting holes deliberately plated+grounded (with stitching) or isolated | M | 4 | AZ, PK, HH, CD |
| 8 | PDN-01 | Decoupling caps as close as possible to power pins; each power pin has its own cap | M (C for fast ICs) | 4 | AZ, JN, KG, CE |
| 9 | PLC-01 | Order: fixed parts → main ICs (CPU/memory) → other ICs → power → small passives | M | 4 | FD, GD, JP, CE |
| 10 | SLK-01 | No silk on pads, drills or exposed copper; silk clipped by mask flagged | M | 4 | AZ, GD, JN, KD |
| 11 | STK-02 | Every signal layer one dielectric from a solid reference plane; no unshielded adjacent signal layers | M | 4 | HT, PK, PS, JL |
| 12 | THM-01 | Thermal reliefs on plane connections for solderability (except intended heat-sinking pads) | M | 4 | AZ, GD, PK, JN |
| 13 | SLK-05 | Revision, date, name/logo; blank box for serial/assembly revision | m | 4 | AZ, HH, JN, GD |
| 14 | DFM-02 | Annular ring ≥ fab/IPC-class minimum (PK: 5 mil Class 2, 7 mil Class 3 for 10 mil vias; AP: >3 mil) | C | 3 | PK, AP, KD |
| 15 | DFM-11 | PTH finished hole ≥ lead + ~0.2 mm (≥10 mil); square pins sized by diagonal; plating allowance; pad ≥ hole ... | C | 3 | GD, JN, HH |
| 16 | HS-01 | Diff pairs routed coupled at impedance gap; uncoupled length limited | C | 3 | AZ, HH, KD |
| 17 | HV-01 | Creepage and clearance sized for voltage, including between layers | C | 3 | GD, HH, KD |
| 18 | MEC-01 | Outline, dimensions and mounting holes match the enclosure/card rack (checked in 3D with accurate models) | C | 3 | AZ, AL, CE |
| 19 | MEC-08 | No part collisions or courtyard overlaps | C | 3 | AZ, KG, KD |
| 20 | PRC-02 | Board/schematic parity: no missing, extra or duplicate footprints; pad nets match schematic; footprint attr... | C | 3 | HH, JN, KD |
| 21 | PRC-03 | Zero unrouted connections / airwires; no polygon breaks | C | 3 | HH, JN, KD |
| 22 | PRC-04 | DRC 100% clean; every excluded/waived violation inspected and signed off | C | 3 | AZ, GD, KD |
| 23 | RF-04 | Antenna/module keep-outs and ground clearance per datasheet | C | 3 | GD, JN, CE |
| 24 | ANA-02 | Sensitive analog physically separated from SMPS/noisy digital | M | 3 | AZ, GD, KG |
| 25 | ASM-02 | Pin-1/polarity marks visible after assembly | M | 3 | GD, JN, HH |

### Inferences
- With no frequency data, a **consensus count** (how many independent checklists flag an item) combined with assigned severity is the best available prior for critic priority. Items with high consensus and Critical severity should be hard gates.
- The respin classes the sources name (footprint/pinout, mechanical fit, open nets, stale outputs) are mostly *verifiable against external truth* (datasheet, MCAD, netlist, fab files). An LLM system adds the most value by grounding against those artifacts, not by "judging" geometry.

### Gaps
- No quantitative survey (respin rate by root cause) was found; vendor surveys (Altium, Siemens, Keysight, Cadence) may exist but were not located. A search for "I made these PCB mistakes" postmortem blogs was cut off by the search budget.

---

## Q6. How do experts evaluate a layout visually ("it looks right"), and can it be quantified?

### Takeaway
The "looks right" heuristics in published checklists are concrete and mostly measurable: consistent orientation of like/polarized parts, grid alignment, text in at most two directions, geographic designators, short/compact power loops, tight decap placement, minimal and uncrossed airwires, traces leaving pads from the end, mitered bends, and repeated channels laid out identically. Each can become a numeric metric. No published study validating aesthetics against electrical quality was found.

### Cited Findings
- "If you have many polarized parts next to each other, place them in the same direction or in a repeatable pattern" to ease human visual inspection. Place components on a coarse grid (1 mm/1.27 mm). Use easy board dimensions. Keep text orientation consistent — [grosdode](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md).
- "All polarized components point same way"; "all legend text reads in one or two directions"; "components labeled left-right, top-bottom"; use mitered 45° bends instead of 90° — [jnoss](https://github.com/jnoss/pcb-checklist).
- "Can components be oriented in roughly the same way / consistency in layout?"; "All text is readable from at most two directions"; "Are component references ordered by PCB layout?"; interactive components placed in a logical, consistent manner — [henrikh](https://github.com/henrikh/pcb-checklist).
- Put footprint origins on a regular grid (5 mil preferred), with the origin at the part's physical XY midpoint so it rotates cleanly. Put vias on a 5 mil grid except for RF transitions and tight BGA breakouts. Arrange capacitors so their power nets face the same direction — [Pikafu](https://github.com/Pikafu/pcb_design).
- The placement goal is to minimize airwire length and crossings — [Autodesk](https://www.autodesk.com/products/eagle/blog/pcb-layout-basics-component-placement/). Connected components close together; use the ratsnest — [KiCad Getting Started](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/getting_started_in_kicad/getting_started_in_kicad.adoc).
- Compactness of power stages: transistor, inductor and caps close together (Feranec, [FEDEVEL forum](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629)); minimize the high-di/dt loop and SW-node area ([TI](https://ti.com/document-viewer/TPS61178/datasheet/layout-guidelines-slvsda71918)).
- Traces should leave SMT pads from the end, not the side (no links between adjacent pads that look like shorts) — [jnoss](https://github.com/jnoss/pcb-checklist); use a U-shaped trace between same-component pins — [grosdode](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md).
- Schematics flow left→right/top→bottom ([Pikafu](https://github.com/Pikafu/pcb_design); [henrikh](https://github.com/henrikh/pcb-checklist)). Layout should reflect physical reality ([henrikh](https://github.com/henrikh/pcb-checklist)).
- KiCad supports regularity directly: Align (left/center/right/top/middle/bottom) and Distribute tools ([KiCad editing docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc)); identical channels via multichannel Repeat Layout ([KiCad multichannel docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_multichannel.adoc)).

### Inferences (proposed quantifications; not from a published source)
| Heuristic (source) | Metric | Computation (KiCad board + netlist) |
|---|---|---|
| Consistent orientation (GD, JN, HH) | Orientation entropy per part class | H = −Σ p(θ) log p(θ) over rotations {0, 90, 180, 270} for footprints sharing a prefix/footprint ID within a block; lower is better. Polarized parts: fraction pointing in the modal direction |
| Grid alignment (GD, PK) | Grid-snap ratio | Fraction of footprint origins (and vias) on a grid g ∈ {0.05 mm, 0.127 mm, 1 mm, 1.27 mm} within ε |
| Alignment/rows (KiCad align tools) | Collinearity score | Count clusters of footprints sharing x or y centers (within ε) among same-class parts; reward rows/columns |
| Minimal, uncrossed airwires (AD, KG) | HPWL + crossing count | Half-perimeter wirelength per net (or MST length) and number of pairwise MST-edge crossings |
| Compact power loops (FD, TI) | Hot-loop area | Polygon area through pad centers of role-tagged loop members (C_in, Q_hi, Q_lo/D, or boost equivalent); also SW-node copper area |
| Decap tightness (AZ, JN, PK) | Decap distance & ordering | Pad-to-pin path length for each cap→pin pair; check that smaller value means shorter distance |
| Text orientation (HH, JN) | Distinct text-direction count | Number of distinct readable directions of silk ref text (target ≤2); mirrored on bottom |
| Geographic designators (HH, JN) | Rank correlation | Spearman correlation of ref number vs (row-major) position per prefix |
| Pad-exit style (JN, GD) | Side-exit count | Track segments attaching to a pad on its long side when the adjacent pin is the same net |
| Bend style (JN, HH) | Angle histogram | Fraction of track-to-track joints at 90° or acute (KiCad `track_angle` can flag them) |
| Channel symmetry (KiCad multichannel) | Layout congruence | After the isomorphism map, RMS positional/rotational deviation of target vs reference channels |
| Signal flow (Pikafu, HH) | Flow monotonicity | For the block graph ordered from input to output connectors, the fraction of inter-block edges pointing "forward" along a chosen board axis |

- These metrics work as **soft objective terms** for placement and as inputs to an LLM judge. That gives it numbers to reason with instead of eyeballing images.

### Gaps
- No empirical study found linking aesthetic regularity to electrical/EMC performance or reviewer acceptance. Metric weights would need calibration (e.g., against expert-rated boards).

---

## Implications for an LLM-driven KiCad placer/router

### Takeaway
Encode the expert workflow as a **backtracking state machine** whose stages mirror the expert sequence and the staged-review practice (pre-layout → placement review → critical-routing review → final). Encode the checklist as a **three-tier critic stack**: (A) KiCad DRC + custom rules, (S) semantic-geometry Python critics driven by a part/net role annotation layer, and (J) an LLM judge, plus simulation hooks, for the rest. Hard-gate Critical items, score Major items, and treat minor/aesthetic items as objective terms.

### Cited Findings (capabilities and prior art the design can build on)
- KiCad's built-in DRC already covers many A-class items: shorts/clearance/creepage, unconnected ends, starved thermals, edge/hole clearances, annular width, microvia rules, courtyard overlap and missing courtyards, copper slivers, mask bridges, schematic parity (missing/extra/duplicate footprints, pad net mismatch, attribute/field mismatch), length/skew/via-count, diff-pair gap/uncoupled length, silkscreen clearance/clipping, text height/thickness, mirrored text, isolated copper, intersecting zones, and footprint-vs-library mismatch. All severities are configurable — [KiCad DRC docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_inspecting.adoc).
- KiCad custom rules provide these constraint types: `annular_width, assertion, bridged_mask, clearance, connection_width, courtyard_clearance, creepage, diff_pair_gap, diff_pair_uncoupled, disallow, edge_clearance, hole_clearance, hole_size, hole_to_hole, length, microvia_aspect_ratio, microvia_stack_depth, min_resolved_spokes, physical_clearance, physical_hole_clearance, silk_clearance, skew, solder_mask_expansion, solder_paste_abs/rel_margin, text_height, text_thickness, thermal_relief_gap, thermal_spoke_width, track_angle, track_segment_length, track_width, via_count, via_dangling, via_diameter, zone_connection`. Conditions can use `A.NetClass`, `enclosedByArea()`, `intersectsArea()`, `intersectsCourtyard()`, `existsOnLayer()`, `fromTo()`, `getField()`, `hasComponentClass()`, `inDiffPair()`, `isCoupledDiffPair()` — [KiCad advanced/custom rules docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc).
- KiCad placement primitives: select by hierarchical sheet, Pack and Move, Move Individually, Auto-Place (ratsnest-simplifying), Align/Distribute — [KiCad editing docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc). Reuse primitives: design blocks and multichannel rule-area generation + isomorphism-checked Repeat Layout — [design blocks](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_design_blocks.adoc); [multichannel](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_multichannel.adoc).
- Review-process precedents: staged reviews ([VSE](https://www.vse.com/blog/a-pcb-layout-checklist-for-error-free-manufacturing/), [Flux](https://www.flux.ai/p/blog/pcb-design-review-process)); per-IC datasheet review ([UWARG](https://uwarg-docs.atlassian.net/wiki/spaces/EL/pages/2173501609)); reviews as Git PRs tied to commits ([UW Rocketry](https://uwaterloo.atlassian.net/wiki/spaces/ROCKETRY/pages/43024155641/Design+Reviews)); commercial guideline-to-checklist knowledge bases ([Zuken DR Navi](https://www.zuken.com/en/resource/datasheet-cr-8000-circuit-dr-navi/)); a CM's DRC run continuously during layout ([MacroFab](https://macrofab.com/blog/five-tips-to-clean-up-your-layout/)).
- LLM prior art: claude-eda ships Claude Code skills/agents (pcb-placement, drc-validator, manufacturing-prep). They encode a 4-tier placement priority (fixed → critical → support → remaining) and numeric distance thresholds as prose for the LLM to follow, with KiCad MCP servers for execution — [l3wi/claude-eda](https://github.com/l3wi/claude-eda). Its thresholds and some claims (e.g., the 2-layer USB impedance claim) are unsourced ([LAYER-COUNT-DECISION.md](https://github.com/l3wi/claude-eda/blob/main/templates/claude/skills/eda-architect/reference/LAYER-COUNT-DECISION.md)).

### Inferences

**1. Agent plan as a state machine** (stages from Q1; each stage's exit gate runs the listed critics)

| State | Inputs / artifacts | Actions (KiCad ops) | Exit critics (checklist IDs) | Gate | Backtrack on failure |
|---|---|---|---|---|---|
| S0 Intake | Schematic, BOM, datasheets, enclosure, fab profile | LLM builds a **constraint & role model**: net classes (HS, diff, RF, power + current, HV + voltage), part roles (decap-of, crystal-of, ESD-of, hot-loop members, FB network, terminations), per-IC layout rules extracted from datasheet "Layout Guidelines"; import fab rules | PRC-01, PRC-05, PRC-07 (rule extraction), PRC-10, FP-01/02/07 | All C pass | Ask human / fix schematic |
| S1 Mechanical | Enclosure/MCAD | Outline, holes, keepouts (rule areas), height zones; lock | MEC-01..14, DFM-10 | C pass | — |
| S2 Stackup | Fab templates, interfaces | Pick minimum layer count; choose fab stackup; compute impedance widths → per-layer net-class rules | STK-01..07 | C pass | Revisited from S8/S12 |
| S3 Fixed parts | Role model | Place/lock connectors, UI, debug headers, heatsinks | MEC-04..06, MEC-12, DFT-04 | C pass | → S1 |
| S4 Floorplan | Hierarchy | One region per sheet (KiCad "Generate Placement Rule Areas" or equivalent); block ordering along signal flow from connectors; domain separation | PLC-02..05, ANA-02, flow-monotonicity metric | Score ≥ threshold | → S1 (area), S3 |
| S5 Critical placement | Datasheet rules | Place BGAs (with trial fanout), power stages (hot-loop minimization), crystals, RF; apply design-block memory if a matching topology exists | PWR-01..03, PLC-07, PLC-12, RF-04, hot-loop metric | C pass; M scored | → S4 |
| S6 Decoupling/support | Role model | Cross-select caps → place per pin (Move Individually analogue); ESD at connectors; terminations | PDN-01..04, PLC-05/06/08 | Distances within datasheet/default thresholds | → S5 |
| S7 Remaining | — | Place rest; snap to grid; orientation normalization; multichannel Repeat Layout for channels | MEC-08 (courtyards), PLC-13..17, aesthetic metrics | 0 overlaps | — |
| S8 Placement review | Full placement | Routability estimate (HPWL, congestion map, quick autoroute trial ≥85%); LLM placement review on renders + metrics | PLC-10, PLC-11, STK-06, J-review | Pass | → S4–S7 (move), S2 (add layers) |
| S9 Fanout | Dense parts | Escape patterns, decap vias | DFM-05, PST-01, PDN-03 | All escaped | → S5 |
| S10 Critical routing | Net priority list | Route diff pairs, clocks, RF, power loops, sensitive analog; return vias | HS-01..06, GND-02/03, RF-01..03, PWR-02..04 | C pass | → S5 / S9 |
| S11 Planes | — | Pours/planes; check splits/antipad slots; island removal | GND-01, GND-04..08, PDN-05..08, ZON-02/03, THM-01/05 | C pass | → S10 |
| S12 Bulk routing | — | Route the rest (router of choice) | PRC-03, RTE-01..07 | 100% routed | → S7 or S2 |
| S13 Tuning | Length budgets | Meanders | HS-02, HS-03 | Pass | → S10 |
| S14 Stitching | — | GND stitching, RF fences, edge stitching | RF-02/03, GND-08, MEC-03 | Pass | — |
| S15 Verify | — | Refill zones; full DRC; parity; DFM margin report | All A-class items; PRC-02..04, ZON-01, CAM-01 | 0 C errors | Local repair → S12 |
| S16 Docs/outputs | — | Silk cleanup, fiducials, fab/assembly drawings, Gerber/drill/X2, independent re-parse | SLK-*, ASM-*, CAM-*, PNL-* | Pass | — |
| S17 Sign-off | Everything | LLM per-IC datasheet review + requirements review; human approval | PRC-06..09, all J items | Human | → any |

- Make every transition **checkpointed** (git commit per state, mirroring the PR-per-review practice) so backtracking is cheap and diffs are reviewable.
- Use **bounded retries** with escalating fixes: local move → block re-floorplan → add layers/increase board area → ask a human. This copies the expert loop of iterate with the ratsnest, then re-plan.

**2. Turning checklist items into critic functions**
- **Tier A (deterministic, cheap; run continuously).** Generate a KiCad custom-rules file from the role/constraint model, then run `kicad-cli pcb drc` (or the IPC API equivalent). Map each DRC violation type to a checklist ID. The table's "Auto" column already names the KiCad check for most A items (e.g., MEC-08 → Courtyards overlap; HS-01 → diff_pair_gap/diff_pair_uncoupled; HV-01 → creepage). Gate on the Critical subset.
- **Tier S (semantic geometry; run at stage exits).** Write a Python critic per item with signature `critic(board, roles, params) -> list[Finding]`. Each Finding carries `{id, severity, objects, measured, threshold, evidence_png, suggestion}`. Core S critics, by consensus × severity:
  1. decap-to-pin distance/ordering (PDN-01/02);
  2. hot-loop area and SW-node area (PWR-01/02);
  3. HS reference-plane continuity: project each HS segment onto its reference layer and intersect with voids/splits/antipad slots (GND-02, PDN-08);
  4. return-via proximity at layer changes (GND-03);
  5. connector-proximity for ESD/interface parts (PLC-05, EMC-01);
  6. current-capacity check: copper width vs net current per IPC-2152-style tables (PDN-06/07);
  7. crystal trace length/guard (PLC-07);
  8. via-fence pitch vs λ/8 for RF nets (RF-02);
  9. thermal-via count under tagged hot pads (THM-02);
  10. pin-1/polarity silk visibility (ASM-02).
  
  Thresholds must be **parameters with provenance**, taken first from the datasheet (S0 extraction, per the per-IC review practice) and only then from defaults such as claude-eda's 3 mm / 5 mm values, which are unsourced.
- **Tier J (LLM judge + simulation).** For items needing intent or external context (MEC-04 connector standards, MEC-06 UI placement, PRC-06 requirements, ANA-01 guard rings, HS-08 pad compensation, GND-04 split justification, option footprints), give the LLM a structured packet: the item text and rationale from this table, relevant datasheet excerpts, the role model, per-layer renders cropped to the objects, and the numeric metrics from Tiers A/S. Require a verdict in {pass, fail, uncertain} with cited evidence. Route "uncertain" to a human. Hand items marked "sim" (HS-08, PWR-01 EMI, thermal) to SI/PI/thermal simulators where available.
- **Scoring.** Critical failures block stage exit. Major findings contribute weighted penalties (weight could follow the consensus count from Q5). Minor/aesthetic metrics (Q6 table) become soft objective terms in the placer's cost function, so neatness is optimized rather than only checked.
- **Placement objective = routability + semantic critics + aesthetics.** HPWL/crossings and congestion (PLC-10/11), plus S-critic penalties (decap distance, loop area, domain separation), plus Q6 regularity metrics. This makes the experts' visual heuristics an explicit, differentiable-ish objective.

**3. Using KiCad's reuse features in the plan**
- Treat hierarchical sheets as floorplan clusters, and generate placement rule areas automatically (KiCad computes a convex hull rectified to 90° per sheet/class/group).
- Detect repeated channels by topology (KiCad's isomorphism check), lay out one reference channel well, and Repeat Layout to the rest. Score channel congruence (Q6).
- Keep a **design-block library as agent memory**: after a sub-circuit passes its S/J critics, save it as a design block keyed by a topology fingerprint plus part numbers. Later boards place the block and re-apply its layout. This automates the expert's copy-the-reference-layout habit.

**4. Coverage implication.** With the table's tags, about a third of items (65 of 190 A or A/S) are fully automatable today with KiCad DRC/custom rules, and another ~43% (82 S or S/J) become automatable once the role annotation layer exists, leaving ~23% (43 J) for LLM/human judgment or simulation. The LLM's main jobs are therefore (a) building the role/constraint model from schematic + datasheets, (b) planning and backtracking through the state machine, and (c) judging the J residue. LLM "eyeballing" of geometry that a critic can compute exactly is not a good use of it.

### Gaps
- No published LLM-agent PCB workflow with evaluated critic coverage was found (claude-eda is prose-encoded and unevaluated).
- Thresholds for many S critics (e.g., acceptable hot-loop area, decap distance by package/frequency) are not standardized in the sources. They need datasheet extraction or calibration against expert-reviewed boards.
- Whether KiCad's IPC API (vs `kicad-cli` and the pcbnew Python bindings) exposes everything needed for Tier A/S critics in the current release was not verified in this research.
