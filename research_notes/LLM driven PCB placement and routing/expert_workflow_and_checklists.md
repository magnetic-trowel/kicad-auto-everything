# Expert PCB layout workflow and design-review checklists (to encode as an LLM-driven KiCad planner + automated critics)

> Research notes, first pass and deep pass, compiled 2026-10-20.
>
> **Provenance markers.** Every citation carries one of two tags:
> - **[P]** means the cited page, PDF or API record was fetched with curl and the claim was checked against its text.
> - **[S]** means the claim rests only on a search-result snippet or summary. The page was not retrieved, or its content is rendered by JavaScript and could not be extracted. Treat [S] wording as approximate.
>
> **Access limits.** In the first pass, almost all non-GitHub/GitLab hosts were blocked. In the deep pass most vendor sites were reachable through curl. These remained unreachable:
> - analog.com (HTTP/2 reset / empty reply);
> - Springer, O'Reilly and Tenlong (JS or bot challenge);
> - Autodesk blog (403);
> - Cadence resources (JS-rendered);
> - old FEDEVEL blog URLs.
>
> The shared web-search budget ran out again late in the deep pass, so some leads were followed only through links inside fetched pages.
>
> **Primary sources read in full** (with dates):
> - 5 GitHub checklist repos (azonenberg, grosdode, Pikafu, henrikh, jnoss).
> - KiCad documentation source on GitLab, plus the KiCad 9.0.0 and 10.0.0 release notes.
> - Altium checklists by Mark Harris (2021-10-25) and Zachariah Peterson; Altium "perils" and "6 areas" articles.
> - Sierra Circuits / ProtoExpress design checklist (2022-06-22), DFA checklist (2026-04-08) and design-review article (2022-10-06).
> - PCB Power 30-item DFM checklist PDF; MacroFab pre-order and clean-up articles; SparkFun manufacturing rules; VSE checklist (2023-03-30).
> - UWARG and UW Rocketry Confluence pages via REST.
> - NASA GSFC-STD-8001A (approved 2026-08-24).
> - TI app notes SPRAAR7J (2023), SZZA009 (1999), SLYT614 (2015), SNVA054 (AN-1229) and SLVAFJ3 (2023).
> - Barry Olney "Beyond Design" columns (Dec 2012 placement/routing strategy; 2024 high-speed rules).
> - Rick Hartley summaries (Altium 2018, ProtoExpress 2023, EE Journal 2018).
> - FEDEVEL forum posts by Robert Feranec, extracted from embedded JSON.
> - KiCad forum threads via the Discourse JSON API.
> - Book tables of contents: Archambeault and Mitzner via Crossref; Ritchey Vol 2 via the publisher PDF; Robertson via InformIT, plus Robertson's sample chapter 2.
> - Respin and DFM statistics sources (Lifecycle Insights citations, Aberdeen via Siemens, PCD&F/Circuits Assembly 2025 survey, Dana Korf 2019, AtlasPCB 2026).
> - Two open-source LLM KiCad-review skill packs: aklofas/kicad-happy and the Adom kicad-board-audit skill.

---

## Q1. What does the expert layout workflow look like, step by step, with its decision points, reasoning, placement-routing iteration and time split?

### Takeaway
Primary expert sources describe the same constraint-first order:
1. Mechanics, stackup and rules.
2. Power/ground strategy.
3. Fixed parts, then functional-block floorplan.
4. Critical parts, decoupling, the remaining parts, and a placement sanity check (a quick test autoroute ≥85%, per Olney).
5. Fanout, often done together with placement.
6. Critical nets routed by hand and locked, then planes, bulk routing, tuning and stitching.
7. DRC/DFM, then outputs.

Placement is where expert judgment concentrates, and it is iterative. "90% placement / 10% routing" and "the last 10% of routing takes 90% of the time" are folk rules, not measurements. Feranec reports 50 h for simple boards and 200 h or more for CPU+memory boards.

### Cited Findings

**Barry Olney (In-Circuit Design), "Interactive Placement and Routing Strategies" (PCB Design Magazine, Dec 2012)**. This is the most complete primary statement of an expert sequence found. [P] — [iConnect007 Beyond Design](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design); [ICD PDF version](https://www.icd.com.au/articles/Interactive_Place_&_Route_PCBDesign-Dec2012.pdf).
- Placement determines route completion. A hard-to-route board "may just be the result of poor placement, slots/gates positioned all over the board, or perhaps the sequence of pins on components are flipped." Open route channels and leave space for vias.
- Place interactively by **cross-probing from the schematic, one component at a time**, "taking functionality and design constraints into account". A select list can't tell "a trivial static pull-up resistor" from "a critical terminator".
- Rework and inspection rules:
  - 80 mil minimum clearance for rework tools.
  - 60° angle for visual inspection, or 45° where possible, which works out to spacing = height of the tallest component.
  - Align similar parts in the same orientation, with all IC pin-1s the same way and memories in a matrix.
  - Placement grid of 100 mil for large parts and 25 mil for chip parts.
- On double-sided boards, align bottom lands with top lands to open space for vias.
- Autoplacement is "one of the most useless features", but it is useful "to see if all the components will fit inside the board outline before starting placement".
- Test the placement by letting the autorouter loose: "If you do not get at least 85% completion on this first test route, then you may need to tweak the placement, look at more appropriate packaging, adjust the design rules, and possibly drop some functionality."
- Before formal routing:
  - Plan the stackup (impedance, clear return path per layer) and move it into the design rules.
  - Plan the PDN and place the bypass caps.
  - Pass rules from the schematic, with via sizes per net class and rule priority set.
  - Set the router options.
- Routing order:
  - Fan out from schematic selections. Power traces are 10–20 mil, and each GND/VCC gets its own via.
  - Route matched-length, differential and critical nets first and **lock them**.
  - Route the remaining nets a few groups at a time, in priority order, driven from the schematic.
- Final sanity check: highlight each net one by one to find nets "longer than the Manhattan length or spiral around the board three times".
- Aesthetic caveat: "if a PCB design looks good, it will probably work well. However, neatness in routing often leads to unwanted crosstalk as trace segments are routed in parallel for long distances."
- Autodesk's often-quoted "85% autoroute" test repeats Olney's rule — [Autodesk blog](https://www.autodesk.com/products/eagle/blog/pcb-layout-basics-component-placement/) [S] (403 to curl).

**Robert Feranec (FEDEVEL)**: forum answers extracted from the embedded JSON. [P]
- Answer to a question about iMX6 placement (2016-11-18): "start with defined components and positions (board shape, mounting holes, connectors), then continue with CPU + memories, other chips, power supplies (chips, inductors, big capacitors), finish with small components." Also: "I do fanout and placement at the same time. Initially I do simple placement under CPU (just to see how many components we have to place there), then I move everything what should be under CPU out of the board and start from middle placing VIAs and components back." Also: "the memories are too close to each other (you will not have space to route tracks between them)", and "transistor + inductor + capacitors should be close to each other". The asker had proposed a five-group order (processor/connectors → decaps → crystal → precise/pull resistors → others) — [FEDEVEL forum "Placement"](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629) [P].
- Decap ordering: "nF closest to the pins, XXuF a little bit further (or around BGA), XXXuF around the BGA or/and on the way from Power to BGA" — same thread [P].
- "We never use autorouter. We always track our time on projects" (2016-07-03). In the same thread a user frames big-board design as schematic → board shape → placement → fan-out → routing, noting that steps 3–5 conflict — [FEDEVEL forum "auto or interactive route"](https://fedevel.com/forum/imx6-rex-tiny-rex-open-rex/3198-auto-or-interactive-route) [P].
- Effort (2016-04-15): "simple boards are up to 50 hours, more complex boards (with a CPU and memory) starts around 200 hours". He works hourly because "projects keep changing during development". The answer links timesheet posts — [FEDEVEL forum "How to price projects"](https://designhelp.fedevel.com/forum/fedevel-academy/course-questions-no-electronic/2472-how-to-price-projects) [P].
- The timesheet posts exist. Their pages carry only meta descriptions; the graphs are images and were not parsed. Examples: "See the length matching, that took quite a lot" — [How long it takes to design a baseboard for a CoM](https://courses.fedevel.com/blog/how-long-it-takes-to-design-a-baseboard-for-computer-on-module) [P, description only]; also [x86 custom board design – how long it takes](https://courses.fedevel.com/blog/x86-custom-board-design-how-long-it-takes) [P, description only].
- Tip #095: "You may want to place all the components on the board before you start doing layout … Sometimes it can be very difficult to add components into already routed areas" — [FEDEVEL Tip 095](https://courses.fedevel.com/blog/tip-095-you-may-want-to-place-all-the-components-on-the-board-before-you-start-doing-layout) [P].
- Sierra Circuits workshop (May 2018):
  - "Using an Impedance Calculator is good but you should always communicate with your manufacturer."
  - On DDR2/3: do not fully route all connections at once. After fully routing selected pin groups, "it became impossible to connect the la[st]…".
  - High-speed rules: route signal groups with the same topology; use stitching vias when the reference changes.
  - On stackup: "always ask your manufacturer for help."
  
  Source: [ProtoExpress workshop report](https://www.protoexpress.com/blog/sierra-pcb-layout-design-workshop-robert-feranec/) [P].

**TI app notes: sub-circuit micro-workflows and routing priority**
- SZZA009 "PCB Design Guidelines for Reduced EMI" (1999), §2.6.3: "Power and ground routing, as well as signals that impact susceptibility, should be laid out by hand. Any signal with clocked data … should be next. Only signals with switching rates below 50 kHz can be left safely to the autorouter. Even then, every signal should be checked for EMI issues. Routing near the crystal … should be checked. Finally, the ground traces should be gridded" — [TI SZZA009](https://www.ti.com/lit/pdf/szza009) [P].
- SLYT614 "Five steps to a great PCB layout for a step-down converter" (Chris Glaser, AAJ 1Q2015) [P] — [TI SLYT614](https://www.ti.com/lit/pdf/slyt614).
  - "a best-practice option with the least risk is to simply copy the PCB layout example found on the evaluation module (EVM) and shown in the datasheet."
  - Otherwise, the order is:
    1. Place the input capacitor and route it immediately ("first component placed in the layout after the IC … so that nothing else can be routed in its path").
    2. Inductor.
    3. Output capacitor.
    4. Small-signal parts.
    5. Single-point ground and vias.
- AN-1229 "SIMPLE SWITCHER PCB Layout Guidelines": "Remaining component placements can be taken up only after the input bypass capacitor and the catch diode are firmly in place." Also: "'Beefing up' traces … should be a last resort. Decreasing the length of the trace should be the first step" — [TI SNVA054](https://www.ti.com/lit/pdf/snva054) [P].
- SLVAFJ3 (LM5177 family) "Steps for a Good Layout":
  1. Identify critical circuit paths.
  2. Optimize hot loops.
  3. Separate differential sense lines from power planes (using net ties).
  4. Route gate-drive and return paths.
  5. Controller layout.
  6. Separate AGND/PGND.
  7. Thermal vias.
  8. Layout example.
  
  Source: [TI SLVAFJ3 PDF](https://www.ti.com/lit/pdf/slvafj3) [P].

**Other practitioner orderings**
- JLCPCB's process guide puts **power-distribution and grounding strategy before placement**: mechanical constraints/outline → stackup and design rules → power distribution and grounding strategy → component layout (functional blocks, "plane iteration based on IC pin distribution", decoupling) → "Critical Signal Routing: Manual First, Always" → remaining routing — [JLCPCB layout process guide](https://jlcpcb.com/blog/pcb-layout-process-guide-2026-mastering-pcb-design) [P, headings]. The placement guide says: "Mechanical constraints, key ICs, supporting passives, secondary components, then a placement sanity check before any routing begins" — [JLCPCB placement guide](https://jlcpcb.com/blog/pcb-component-placement-guide-2026) [P]. The routing guide says: "Route power loops, high-speed signals, differential pairs, and sensitive analog paths while the board is open" — [JLCPCB routing rules](https://jlcpcb.com/blog/pcb-routing-rules-best-practices) [P].
- Electronics-notes (Ian Poole): "Identify and route layout critical tracks … By routing these tracks at this stage, then the remain[der] of the design can be implemented around these tracks." Then route power and earth rails, often as planes — [electronics-notes](https://www.electronics-notes.com/articles/analogue_circuits/pcb-design/pcb-layout-routing.php) [P].
- PCD&F June 2019 "PCB Guided Insights": "90% of the routing on a PCB takes only 10% of the time, while 10% of the remaining routing can take 90% of the time … The routing challenge will most certainly turn into defeat and a complete do-over if the remaining 10% of the routing includes any critical signals … Avoid complete routing do-overs by routing critical lines first" — [PCD&F 2019](https://www.qgdigitalpublishing.com/article/PCB+Guided+Insights/3388181/589425/article.html) [P].
- KiCad forum (2020), "Strategy to use for placing components" [P] — [KiCad forum 23682](https://forum.kicad.info/t/strategy-to-use-for-placing-components/23682):
  - @kenyapcomau: "it's an iterative process … watch what happens to the rats nest … Then I hit some constraint and I may have to try a different layout … Sometimes I even modify the circuit."
  - @Rerouter: group each chip's private parts first, "move them around until the least number of traces would have to cross", then arrange groups into functional blocks.
  - @eelik: group functionally in the schematic; place interface parts first; "If you don't have any need to limit the size of the board, don't limit it too much. Usually the needed space … [is] underestimated"; draw the most important traces first; then "move and rotate … draw tracks, refine them and delete and redraw them iteratively."
- KiCad's Getting Started guide: outline → place (fixed-location parts, electrical constraints, non-overlapping courtyards, then ratsnest-driven) → route → DRC → outputs — [KiCad Getting Started source](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/getting_started_in_kicad/getting_started_in_kicad.adoc) [P].
- MIT 2.996 handout: "Place all the components before routing any traces. Use the rat's nest lines…", and keep decaps near components — [MIT handout mirror](https://mitocw.ups.edu.ec/courses/mechanical-engineering/2-996-biomedical-devices-design-laboratory-fall-2007/labs/lab_handout3.pdf) [P].
- SparkFun's house rules: "The autorouter can only be used on prototypes. Hand routing and touch-up of the autorouter is expected for production boards" — [SparkFun: Designing for SparkFun manufacture](https://learn.sparkfun.com/tutorials/how-to-sell-your-widget-on-sparkfun/designing-for-sparkfun-manufacture) [P].

**Review gates (iteration checkpoints)**
- UW Rocketry asks for reviews at three points, on the same PR: (1) after schematics; (2) "When you've roughly laid out your PCB but haven't done any routing (… it's much easier to make significant layout changes before doing routing)"; (3) when the PCB is complete. The reviewee posts the checks performed, and reviews are tied to a commit — [UW Rocketry Design Reviews](https://uwaterloo.atlassian.net/wiki/spaces/ROCKETRY/pages/43024155641/Design+Reviews) [P].
- VSE: "many PCB design departments will have multiple design reviews with different checklists for each review. These could include a pre-layout review, a component placement review, and a critical routing review" — [VSE layout checklist (2023-03-30)](https://www.vse.com/blog/a-pcb-layout-checklist-for-error-free-manufacturing/) [P].
- Flux separates schematic review, layout review and DFM review — [Flux design review process](https://www.flux.ai/p/blog/pcb-design-review-process) [P].

**Physics framing (Hartley, Bogatin)**
- Hartley: "The most critical item is the board stackup, and it's what people most often get wrong." Energy is in the dielectric between layers. He disowns his own ~15-year-old paper "Board Stackup to Control EMI": "Ignore this paper because the physics have changed" — [Altium summary (2018-07-24)](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley) [P].
- Hartley: "To contain the fields and control the current, the line should be placed one dielectric away from the ground plane. If not, it will lead to grounding problems" — [ProtoExpress (2023-01-17)](https://www.protoexpress.com/blog/rick-hartley-pcb-design-recommendations-to-minimize-emi/) [P]. On layer changes: "you have to take the fields through the dielectric … You can't just ignore the fields" — [AltiumLive 2019 keynote write-up](https://design.iconnect007.com/article/120662/altiumlive-frankfurt-2019-rick-hartley-keynote/120665/design?page=2) [P].
- Bogatin "break[s] down problems into six families" (reflection, crosstalk, ground bounce, …). The return path follows directly under the signal unless the plane is broken — [EE Journal "Matters of Integrity" (2018-10-23)](https://eejournal.com/article/matters-of-integrity) [P].
- Olney (2024): "All signal layers should be adjacent to a reference plane"; "If there are multiple ground planes, then place a stitching via as close as possible to each layer transition" — [Beyond Design: High-speed Rules of Thumb](https://iconnect007.com/article/143099/beyond-design-highspeed-rules-of-thumb/143096/design) [P].

**Time split**
- Siemens: "Studies have shown that a majority of design time is spent on placement and routing" (no study cited) — [Siemens blog 2022](https://blogs.sw.siemens.com/electronic-systems-design/2022/11/23/pcb-design-physical-layout) [P]. The 2019 post claims automation can "accelerate design cycle times up to 50% or more" (vendor claim; the "up to 80%" figure in my first pass came from a search snippet and was **not** found on the page) — [Siemens blog 2019](https://blogs.sw.siemens.com/electronic-systems-design/2019/04/02/reduce-design-time-using-routing-automation-part-1/) [P].
- DeepPCB: "Most of the time in PCB design isn't spent routing … Constraint definition alone can take days on a complex board" — [DeepPCB](https://deeppcb.ai/pcb-design-timeline-compression/) [P].
- The "90% placement and 10% routing" saying — [Autodesk webinar post](https://www.autodesk.com/products/fusion-360/blog/eagle-first-flights-webinar-surveying-part-placement/) [S]; [PCB Power social post](https://social.pcbpower.com/we-often-hear-this-saying-in-the-electronics-community-pcb-design-is-90-placement-and-10-routing-we-always-2344200531386298630) [S].
- Feranec's measured totals (50 h / 200 h) and "length matching … took quite a lot" are above [P].

#### Ordered workflow model (synthesized; each step backed by the cited sources)

| # | Stage | What experts do | Decision points / reasoning | Exit criterion | Typical loop-back | Key sources |
|---|---|---|---|---|---|---|
| 0 | Pre-layout intake | Schematic reviewed (gate 1). Constraints captured: net classes, impedance, currents, voltages, critical nets. Fab/assembler capability loaded as rules. Libraries and footprints verified | Which nets are critical? Which fab/IPC class? Rules come before routing (Olney: rules from schematic, via sizes per class, rule priority) | Sign-off; rules = fab capability | — | [BO][bo] [P], [VSE][vse] [P], [AZ][az] [P], [Pikafu][pk] [P] |
| 1 | Outline & mechanics | Outline, holes, keepouts, height zones, connector locations from MCAD; round dimensions, coarse grid | Enclosure fixes size. Don't over-constrain size when free (eelik) | Outline closed; holes/keepouts locked | From 8 if area is short | [Pikafu][pk], [grosdode][gd], [Feranec][fdf], [KF][kf] [P] |
| 2 | Stackup, rules, PDN/ground strategy | Minimum layer count; fab standard stackup; impedance widths per layer; decide planes/pours and ground strategy | Hartley: stackup is most critical. Feranec: ask the fab. JLC: decide power/ground strategy before placement | Stackup agreed with fab; net classes set | From 8/12 if too dense | [Hartley][hta] [P], [JLC proc][jlcp] [P], [craftyjon][kfs] [P] |
| 3 | Fit check | Quick autoplace or area estimate to see whether everything fits the outline | Olney's only use for autoplace | Parts fit | → 1 (bigger board) or repackage | [BO][bo] [P] |
| 4 | Fixed parts | Connectors, UI, mounting, heatsinks, debug headers | Mechanical standards, keying, usability | Locked | — | [AZ][az], [KiCad GS][kg] [P] |
| 5 | Floorplan by function / signal flow | Group each IC's private parts; cluster into functional blocks; separate power/analog/digital/RF; order along signal flow | Fewest crossings between groups (Rerouter); place by cross-probing by importance (Olney) | Regions assigned | Moves after 6–9 | [KF][kf] [P], [BO][bo] [P], [Flux][fxp] [S] |
| 6 | Critical parts | BGAs/CPU/memory (with trial fanout), power stages (input cap placed **and routed** first), crystals, RF, terminations | Hot-loop area; memory routing channels; crystal isolation (TI: no unrelated parts within 1 inch) | Critical parts placed and escape-feasible | Iterate with 10 | [Feranec][fdf] [P], [TI SLYT614][slyt614] [P], [TI SZZA009][szza009] [P] |
| 7 | Decoupling | nF at pins, µF near, bulk on the path from the source; own vias per cap | Frequency-staged ordering | Every power pin has a cap within threshold | — | [Feranec][fdf] [P], [AL][alh] [P], [UWARG][uw] [P] |
| 8 | Remaining parts | Everything else placed before routing; orientation and grid regularity | Avoid inserting parts into routed areas later | 0 unplaced, 0 courtyard overlaps | — | [Tip 095][fd095] [P], [BO][bo] [P] |
| 9 | Placement review (gate 2) | Ratsnest inspection; test autoroute ≥85%; formal placement review | Packaging, rules, layer count, or dropping functions | Pass | → 5–8, or → 2 (add layers) | [BO][bo] [P], [VSE stackup][vses] [P], [UW Rocketry][wat] [P] |
| 10 | Fanout/escape | BGA/QFN escape, decap vias | Feranec does this together with step 6 | All escaped | → 6 | [Feranec][fdf] [P] |
| 11 | Critical routes | Matched-length, differential, clocks, RF, power loops, susceptible signals; by hand; lock | Return-path continuity; via symmetry; DDR: don't fully route groups one at a time | Critical nets meet rules | → 6 | [BO][bo], [TI SZZA009][szza009], [TI SPRAAR7][spraar7], [Feranec ws][fdws] [P] |
| 12 | Planes/pours | Solid GND references; power pours; avoid splits/antipad slots | Split only with justification | Planes continuous under critical nets | → 11 | [Hartley][hta], [Flux gnd][fxg] [P] |
| 13 | Bulk routing | Remaining nets interactively, in priority groups | Only low-speed (<50 kHz) nets are safe for an autorouter (TI 1999) | 0 unrouted | → 8 or → 2 | [BO][bo], [TI SZZA009][szza009], [SparkFun][sf] [P] |
| 14 | Length/skew tuning | Meanders at the mismatched end | Tolerances from the interface spec | Length/skew rules pass | → 11 | [TI SPRAAR7][spraar7] [P] |
| 15 | Stitching/fencing | GND stitching at layer transitions; RF fences | Pitch set by frequency | Pass | — | [BO HS][boh] [P], [Pikafu][pk] [P] |
| 16 | Verify | DRC (with silenced-rule audit), parity, DFM; per-net highlight sanity pass | DRC passes functionally wrong boards | 0 errors | Local repair | [BO][bo], [Adom][adom] [P], [Altium perils][al3] [P] |
| 17 | Silk, docs, outputs | Silk cleanup, fiducials, fab/assembly drawings, zone refill + DRC, Gerber+drill together, independent viewer | — | Outputs verified | — | [AZ][az], [PCB Power][pp] [P], [Sierra][sc] [P] |
| 18 | Final review (gate 3) | Per-IC datasheet review; requirements review; reviewer sign-off tied to a commit | — | Signed | → any | [UWARG][uw], [UW Rocketry][wat] [P] |

[bo]: https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design
[boh]: https://iconnect007.com/article/143099/beyond-design-highspeed-rules-of-thumb/143096/design
[vse]: https://www.vse.com/blog/a-pcb-layout-checklist-for-error-free-manufacturing/
[vses]: https://www.vse.com/blog/multilayer-pcb-stackup-planning/
[az]: https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md
[pk]: https://github.com/Pikafu/pcb_design
[gd]: https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md
[fdf]: https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629
[fd095]: https://courses.fedevel.com/blog/tip-095-you-may-want-to-place-all-the-components-on-the-board-before-you-start-doing-layout
[fdws]: https://www.protoexpress.com/blog/sierra-pcb-layout-design-workshop-robert-feranec/
[kf]: https://forum.kicad.info/t/strategy-to-use-for-placing-components/23682
[kfs]: https://forum.kicad.info/t/about-stack-up-selection/21123
[kg]: https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/getting_started_in_kicad/getting_started_in_kicad.adoc
[hta]: https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley
[jlcp]: https://jlcpcb.com/blog/pcb-layout-process-guide-2026-mastering-pcb-design
[fxp]: https://docs.flux.ai/tutorials/component-placement
[fxg]: https://www.flux.ai/p/blog/pcb-grounding-techniques
[slyt614]: https://www.ti.com/lit/pdf/slyt614
[szza009]: https://www.ti.com/lit/pdf/szza009
[spraar7]: https://www.ti.com/lit/pdf/spraar7
[alh]: https://resources.altium.com/p/pcb-design-and-review-checklist
[al3]: https://resources.altium.com/p/how-to-navigate-the-perils-of-pcb-design-review
[uw]: https://uwarg-docs.atlassian.net/wiki/spaces/EL/pages/2173501609
[wat]: https://uwaterloo.atlassian.net/wiki/spaces/ROCKETRY/pages/43024155641/Design+Reviews
[sf]: https://learn.sparkfun.com/tutorials/how-to-sell-your-widget-on-sparkfun/designing-for-sparkfun-manufacture
[adom]: https://wiki.adom.inc/adom/kicad-board-audit/files/SKILL.md
[pp]: https://www.pcbpower.com/static/base/images/resources/DFM_Checklist.pdf
[sc]: https://www.protoexpress.com/blog/pcb-design-checklist-to-build-flawless-board/

### Inferences
- Experts front-load nearly all their judgment into steps 0–9. The routability gate (Olney's 85% test, VSE's "autorouter should nearly be able to complete") is the explicit, quantified decision point between placement and routing. An automated system should spend most of its search effort on placement, with a fast routability estimator as the inner-loop objective.
- Three nested micro-workflows recur. They are natural sub-plans for an agent:
  - **Power-stage micro-workflow**: IC → input cap (place and route) → inductor/diode → output cap → small-signal → ground tie (TI SLYT614/AN-1229).
  - **BGA micro-workflow**: trial placement under the CPU → clear → fanout from the center → decaps nF→µF→bulk (Feranec).
  - **Routing-priority tiers**: power/ground and susceptible nets → clocked data → everything else; only <50 kHz nets are autorouter-safe (TI SZZA009). Olney: matched/differential/critical first and locked.
- Feranec's DDR lesson ("don't fully route all at once") argues for **escape-and-reserve, then complete**: the router should reserve channels for every net in a group before finishing any of them. That fits a negotiated-congestion or rip-up router better than greedy sequential routing.
- The time folklore ("90/10 placement", "last 10% of routing takes 90% of the time") is consistent with Feranec's measured 50–200 h totals, but no primary source splits those hours by phase in extractable form.

### Gaps
- Feranec's timesheet graphs (phase-by-phase hours) are images on JS-rendered pages and were not extracted. His linked "x86 Motherboard Development Process – Step by Step" post now redirects to a dead page.
- Hartley/Bogatin talk transcripts about placement order and Phil's Lab content are covered by the separate practitioner_discussions.md agent.
- Cadence's "What is PCB layout" and placement-checklist pages are JS-rendered (403 or empty); findings from them stay [S].

---

## Q2. How do experts decide board size, layer count and stackup?

### Takeaway
Board size is an input, set by the enclosure, unless the product is free-form. Practitioners warn against over-constraining it, because "space … [is] underestimated", and use an autoplace or area fit test before placing.

Layer count is the minimum that gives every high-speed signal a solid reference plane, every power domain enough copper and fine-pitch parts an escape path, with margin when channel use is high. It is validated with a test autoroute. The stackup is chosen from the fab's standard stackups or co-designed with the fab. Hartley and Ritchey both stress that the stackup is too important to leave implicit.

### Cited Findings
- "Define size, shape, and mechanical features prior to starting layout"; "Start with a small layer count then increase if you need it"; every signal layer needs at least one GND reference; consider panelization efficiency — [Pikafu/pcb_design](https://github.com/Pikafu/pcb_design) [P].
- "If you don't have any need to limit the size of the board, don't limit it too much. Usually the needed space and the space taken by the components+connections are underestimated" — [KiCad forum, eelik](https://forum.kicad.info/t/strategy-to-use-for-placing-components/23682) [P].
- Use autoplacement only "to see if all the components will fit inside the board outline before starting placement. If not, then you can re-evaluate the packaging or reduce functionality" — [Olney 2012](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design) [P].
- Jon Evans (craftyjon, KiCad lead developer), 2020:
  - "I first try to pick the layer count (based on routing complexity) and the board thickness (based on mechanical constraints)."
  - Then take a fab standard stackup and compute widths with a calculator. If the required width is unreasonable, the reference-plane distance is wrong, so either pick another standard stackup (possibly a non-1.6 mm thickness) or ask the fab for a custom one.
  
  Source: [KiCad forum: About stack up selection](https://forum.kicad.info/t/about-stack-up-selection/21123) [P].
- NextPCB rule: choose "the minimum" layer count giving "every high-speed signal … a continuous reference plane, every power domain … adequate copper, and every fine-pitch component [a clean] escape. Then add one pair of layers as margin if your routing density exceeds 70% of available channels" — [NextPCB](https://www.nextpcb.com/blog/how-many-layers-can-a-pcb-have) [P].
- VSE: "To run a quick check on the feasibility of the layer count, run the autorouter. An autorouter should be nearly able to complete routing on its own if the layer count is adequate … The goal … is not to offer guidance but to evaluate the routing density — doubling as a valuable assessment of component placement" — [VSE stackup planning](https://www.vse.com/blog/multilayer-pcb-stackup-planning/) [P].
- Hartley: stackup is "the most critical item … what people most often get wrong". With 2–3 signal layers per plane, "all fields intermingling in the dielectric space … that's one of the places where EMI comes from" — [Altium/Hartley](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley) [P].
- Feranec: "you should not try to do a stack-up by yourself and always ask your manufacturer for help" (said as a joke before his real explanation) — [ProtoExpress workshop](https://www.protoexpress.com/blog/sierra-pcb-layout-design-workshop-robert-feranec/) [P].
- TI SZZA009 has sections on "Two-Layer vs Four-Layer Boards" and "Power Plane Do's and Don'ts for Four-Layer Boards":
  - Pay attention to holes and cutouts in planes, because they increase loop areas.
  - Avoid buried traces in the ground plane (put them in the +V plane if needed).
  - For 2-layer boards: power/ground trace length:width ≤3:1, and power and ground run over each other.
  
  Source: [TI SZZA009](https://www.ti.com/lit/pdf/szza009) [P].
- Altium (Peterson) on fab interdependence: board dimensions/thickness, copper weight vs feature sizes, impedance structures vs stackup, via fill, slots, precision holes, layer registration and surface finish "cannot be evaluated independently because changing one fabrication parameter can change several layout constraints at once". HDI and rigid-flex constraints are "entirely driven by the stackup design", which "needs to be approved by a fabricator … before design rules can be developed" — [Altium layout review checklist](https://resources.altium.com/p/pcb-design-review-checklist-gets-you-manufacturing-quickly) [P].
- Altium (perils): "Board thickness (you'd be surprised how often this is overlooked)" — [Altium](https://resources.altium.com/p/how-to-navigate-the-perils-of-pcb-design-review) [P].
- Robertson (2003) gives fabrication "technology" tiers from a survey of US manufacturers:
  - Conventional: 6/6 mil at 0.5 oz, 12 mil minimum finished drill, 8–10 layers.
  - Advanced: 5/5 mil, 8 mil drill, 15–20 layers.
  - Leading edge: about 2/2 mil, 6 mil drill, 25–30 layers.
  
  "The designer should not use these values unless necessary. It is advisable to leave room for change and not always force the manufacturer to the limits." Fab notes should be "in order of the manufacturing process, to provide a checklist for the manufacturer" — [Robertson, sample ch. 2 (InformIT PDF)](https://www.informit.com/content/images/0130674818/samplechapter/0130674818_ch02.pdf) [P]. The numbers are 2003-era and dated, but the tiering concept is still useful.
- Ritchey & Zasio, *Right the First Time* Vol 2 (Speeding Edge) relevant ToC entries:
  - 2 "The PCB Design Process" (virtual prototyping; a design rule set in "technology table" format; a "preroute rats nest or wire load plot");
  - 3.11 "The Four Layer PCB Problem";
  - 4.6 "Designing the PCB Stackup";
  - 4.8 "Pad Stack Design and Drill Size Choices";
  - 6.1 "Split Planes";
  - 6.2 "How Return Currents Find Their Way from Plane to Plane When a Signal Changes Layers";
  - 7.15 "EMI Rules-Of-Thumb";
  - 8.9 "Length Matching To Connectors";
  - 9.3 "Floor Planning Tools";
  - Appendix 3 "A Generic PCB Fabrication Specification".
  
  Source: [Ritchey Vol 2 ToC PDF](https://speedingedge.com/wp-content/uploads/TABLE-OF-CONTENTS3307-Vol-2.pdf) [P]. Vol 1 (Ritchey & Zasio, ed. Kella Knack, 2003, 288 pp, "48 short chapters") — [Speeding Edge product page](https://speedingedge.com/products/right-first-time/) [P]; [Electronic Design review](https://www.electronicdesign.com/technologies/components/interconnects/article/21775386/right-the-first-time) [P]. Only an expanded *index* of Vol 1 (2005) was retrievable; it lists topics such as "Capacitor placement 147", "Capacitor via length 143" and "10 layer PCB stackup 165" — [Vol 1 index PDF](https://speedingedge.com/wp-content/uploads/Newbookindex.pdf) [P].
- JLCPCB says complicated FPGA/SoC/RF boards "frequently require 6 to 8 or more layers" — [JLCPCB multilayer stackup](https://jlcpcb.com/blog/multilayer-pcb-stackup) [S] (sentence not found on the current page). The ProtoExpress "≤4 lamination cycles" — [ProtoExpress stackup guide](https://www.protoexpress.com/pcb-design-guides/pcb-stack-up-design-guide/) [S] (not found on the current page). Symmetric stackups to prevent warpage are confirmed — [PCB Power checklist §3B](https://www.pcbpower.com/static/base/images/resources/DFM_Checklist.pdf) [P]; [ProtoExpress review article](https://www.protoexpress.com/blog/how-to-perform-pcb-design-review-and-layout-clean-up/) [P].
- NASA GSFC-STD-8001A (2026): PCBs "shall be designed in accordance with IPC-2221 (Class 3)" plus the relevant sectional standard (2222 rigid, 2223 flex, 2226 HDI, 2228 RF), with test coupons designed into all production panels — [GSFC-STD-8001A](https://standards.nasa.gov/system/files/tmp/GSFC-STD-8001A_Approved.pdf) [P].
- Prior-art LLM skill (claude-eda) encodes a 2/4/6-layer table and claims "2-layer with USB: can't achieve 90Ω differential impedance" — [claude-eda LAYER-COUNT-DECISION.md](https://github.com/l3wi/claude-eda/blob/main/templates/claude/skills/eda-architect/reference/LAYER-COUNT-DECISION.md) [P]. That claim is unsourced and too broad.

### Inferences
- An agent's **size decision** can be a two-stage test:
  1. Area estimate: Σ(courtyard areas)/utilization plus edge keepouts, then rounded to easy numbers.
  2. Olney's fit test: run a quick packer/autoplacer inside the outline. If it fails, enlarge the board, repackage, or flag the requirement conflict.
- **Layer count** is generate-and-test. Start from the NextPCB/Hartley minimum, run placement plus a test route, and add a pair if channel use is >70% or completion is <85–100%.
- **Stackup** should be chosen from fab catalog templates, using craftyjon's "impedance width sanity" check: an unreasonable width means pick another template.
- Hi-rel mode (NASA) sets IPC Class 3 rules and coupon requirements globally.

### Gaps
- No published quantitative model links board area or layer count to cost and yield (vendor-specific).
- Ritchey Vol 1 ToC was not retrievable (only the index). The text of the "four layer PCB problem" section was not accessible.

---

## Q3. How do experts use schematic hierarchy and reuse layouts (datasheet/EVM layouts, channel copies, snippets, KiCad design blocks, multichannel)?

### Takeaway
The schematic's functional grouping becomes the floorplan's skeleton. Experts place by cross-probing, group private parts per IC, and then arrange blocks. For power ICs, the lowest-risk move experts and vendors recommend is to **copy the datasheet/EVM layout**.

KiCad now supports this directly, in two releases:
- **KiCad 9.0.0 (Feb 2025)**: multi-channel Repeat Layout, component classes and schematic design blocks.
- **KiCad 10.0.0 (March 2026)**: PCB design blocks (saved layout fragments).

### Cited Findings
**Version history (verified against release notes)**
- KiCad 9.0.0 release notes:
  - "Multi-channel design support: Tomasz Wlostowski contributed support for creating multi-channel designs. This allows the user to repeat PCB layout elements from one channel to create identical copies."
  - "Component classes" (James Jackson): symbols and footprints grouped into classes that can carry DRC rules, with new DRC functions for querying them.
  - "Design blocks: Mike Williams contributed the schematic design blocks implementation … This feature will be extended to include reusable PCB layout blocks in a future version of KiCad."
  
  Source: [KiCad 9.0.0 Released (kicad.org, 2025-02)](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/) [P].
- KiCad 10.0.0 release notes: "PCB Design Blocks: Mike Williams continued his efforts from KiCad 9 and extended the Design Blocks feature to the PCB editor. Users can now create and manage libraries of board layouts." Also new: schematic grouping, design variants and jumpers — [KiCad 10.0.0 Released (kicad.org, 2026-03)](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/) [P].

**KiCad mechanics (current master documentation)**
- Select footprints by sheet (Select → Items in Same Hierarchical Sheet). Cross-selection from the schematic. Pack and Move (P). Move Individually (Ctrl+M), with the documented recipe of selecting bypass caps in the schematic, then Move Individually to place each near its IC. Auto-Place exists — [KiCad PCB editing docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc) [P].
- PCB design blocks:
  - Saved in `.kicad_blocks` libraries.
  - "Typically, design blocks are created first as a schematic fragment, with layout added later."
  - A saved layout can be applied to the footprints of a placed schematic block, or placed directly (e.g., a mounting-hole pattern).
  - Options include "Place as group", "Keep annotations" and "Save to Linked Design Block".
  
  Source: [KiCad PCB design blocks docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_design_blocks.adoc) [P].
- Multichannel:
  - Channels are defined by repeated hierarchical sheets (recommended), component classes or named groups.
  - Equivalent channels need the same symbol count, prefixes, footprints and connections; values may differ.
  - "Generate Placement Rule Areas" builds a convex hull per channel, rectified to a 90° polygon.
  - Repeat Layout runs a topology **isomorphism** check before copying the reference channel to its targets.
  
  Source: [KiCad multichannel docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_multichannel.adoc) [P].

**Expert practice**
- Olney: "When an engineer creates the schematic he invokes a logical process, typically, grouping components into blocks or sheets that functionally go together. When the PCB designer then places these components, he should also use a logical, sequential process … Resistors are just resistors—unless you know what they do. This is the beauty of cross-probing" — [Olney 2012](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design) [P].
- KiCad forum: group functionally in the schematic ("Connectors have their TVS components, regulators have their capacitors") and lay out small groups first, then functional blocks — [KiCad forum 23682](https://forum.kicad.info/t/strategy-to-use-for-placing-components/23682) [P].
- TI: "a best-practice option with the least risk is to simply copy the PCB layout example found on the evaluation module (EVM) and shown in the datasheet" — [TI SLYT614](https://www.ti.com/lit/pdf/slyt614) [P]. Datasheets carry "Layout Guidelines" sections — [TPS61178](https://ti.com/document-viewer/TPS61178/datasheet/layout-guidelines-slvsda71918) [P]; [TPS55330](https://www.ti.com/document-viewer/TPS55330/datasheet/layout-guidelines-slvsbx81345) [P]. App notes such as SLVAFJ3 end with a "Layout Example" — [SLVAFJ3](https://www.ti.com/lit/pdf/slvafj3) [P].
- ADI FAQ (LFCSP exposed pad) points to AN-772 and notes that users import evaluation-board Gerbers as a guide — [ADI FAQ](https://www.analog.com/en/resources/faqs/faq_what_pcb_layout_recommendations_for_exposed.html) [S] (analog.com unreachable).
- Feranec's schematic-checking procedure: "If you compare your schematic to the schematic of an existing and working board, there is a pretty high chance, that your board will work at the first time." "Ideally, if you can find a reference circuit, which exactly fits to your needs, use it" — FEDEVEL page content found embedded in [a FEDEVEL blog page](https://courses.fedevel.com/blog/how-long-it-takes-a-junior-engineer-to-design-an-advanced-board) [P] (this text is the page's embedded "Schematic Page Checking Procedure", not the timesheet).
- Per-IC review against datasheet guidance: "Basically anything that has an IC, have someone review the layout of that circuit and make sure it fits with the layout recommendations in the IC's datasheet" — [UWARG](https://uwarg-docs.atlassian.net/wiki/spaces/EL/pages/2173501609) [P]. Adom's audit skill compares regulator rail sizing and PHY/MAC crossovers "to the vendor EVB" — [Adom kicad-board-audit](https://wiki.adom.inc/adom/kicad-board-audit/files/SKILL.md) [P].

### Inferences
- KiCad version gating matters for an agent:
  - Multichannel Repeat Layout and component classes need ≥9.0.
  - PCB design blocks (layout memory) need ≥10.0.
  - On KiCad 9, layout reuse means multichannel channels or copy/paste of groups.
- The highest-value reuse primitive is **"EVM layout → design block"**. Digitize or import the vendor reference layout for a power IC once, store it as a PCB design block keyed by MPN and topology, and apply it whenever that IC appears. This automates the TI-recommended "least risk" path.
- Hierarchy gives a cheap placement prior. Per-sheet rule areas (KiCad's generator) can serve as floorplan cells. Repeated sheets are detected by KiCad's isomorphism check and handled by Repeat Layout.

### Gaps
- Primary text on Altium "snippets/device sheets" or OrCAD reuse workflows was not retrieved.
- analog.com was unreachable, so ADI AN-772 and the ADI layout notes could not be read.

---

## Q4. Consolidated, de-duplicated master layout-review checklist

### Takeaway
Merging about 30 checklists and guides gives **about 300 distinct layout-review items** across 24 categories (exact counts below). The sources are open-source repos, vendor/fab checklists (Altium, Sierra Circuits, PCB Power, MacroFab, SparkFun, VSE, JLC), team checklists (UWARG, UW Rocketry), standards (NASA GSFC-STD-8001A), TI app notes, expert columns (Olney) and KiCad's DRC catalogue.

By primary tag, about 37% are pure geometry/DRC checks, about 41% need net/part semantics, and about 22% need judgment, external data or simulation. 34 of the 41 Critical items are at least semi-automatable. *Severity and automation tags are my assignments, based on each source's stated rationale.*

### Cited Findings

**Source checklists** ([P] = read in full; [S] = snippet only)
- **AZ** Andrew Zonenberg *pcb-checklist*: 72 layout and 60 schematic items. "Nearly every line item here came from the school of hard knocks" — [layout](https://github.com/azonenberg/pcb-checklist/blob/master/layout-checklist.md), [repo](https://github.com/azonenberg/pcb-checklist) [P]. His company Antikernel Labs runs an internal review checklist of "over 120 different potential problems" that is not public — [Antikernel PCB](https://www.antikernel.net/pcb.html) [P].
- **GD** grosdode — [pcb_checklist.md](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md) [P].
- **PK** Pikafu — [README](https://github.com/Pikafu/pcb_design) [P].
- **HH** Henrik Hansen (pcbchecklist.com) — [repo](https://github.com/henrikh/pcb-checklist) [P].
- **JN** jnoss — [repo](https://github.com/jnoss/pcb-checklist) [P].
- **KD** KiCad DRC catalogue and custom rules — [inspecting](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_inspecting.adoc), [advanced](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc) [P].
- **AL** Mark Harris, Altium "PCB Design Review Checklist" (2021-10-25) [P] — [Altium checklist](https://resources.altium.com/p/pcb-design-and-review-checklist).
  - Sections: Before Submitting; Layers; Signal Path; Components; Testing; Protection/EMI/EMC; Panels.
  - Notable items: a design rule to catch single-pin nets; bypass caps "under 15mm"; separate VCC and GND vias per decap; check traces longer than 1/6 of rise time; TVS pads in series with the track; widths calculated for tracks >100 mA (use internal-layer values without airflow); test points all on one side; panel frame, fiducials, origin mark, coupons and V-score layers.
- **ALP** Zachariah Peterson, Altium "A PCB Layout Review Checklist Gets You to Manufacturing Quickly" [P] — [Altium](https://resources.altium.com/p/pcb-design-review-checklist-gets-you-manufacturing-quickly).
  - Covers DFM points for all designs and advanced fab interdependencies.
  - HDI items: dielectric thickness, stacked vs staggered microvias, laser-via annular rings.
  - Rigid-flex table: bend radius, routing through bends, transitions, vias near flex, components out of bends, coverlay, stiffeners, flex construction, overlapping copper, impedance through flex.
  - BOM/netlist/schematic discrepancies are "one of the most common errors seen during a PCB design review".
- **AL3** Altium "perils": "many electrically or functionally incorrect design choices … will still pass design rule checks"; "board thickness (you'd be surprised how often this is overlooked)" — [Altium](https://resources.altium.com/p/how-to-navigate-the-perils-of-pcb-design-review) [P]. **AL6** "6 Areas …": requirements and traceability, version-control baselines, supply chain, DFM, compliance — [Altium](https://resources.altium.com/p/pcb-design-review-focus) [P].
- **SC** Sierra Circuits (Poulomi Ghosh), "PCB Design Checklist to Build a Flawless Board" (2022-06-22) [P] — [ProtoExpress](https://www.protoexpress.com/blog/pcb-design-checklist-to-build-flawless-board/).
  - Sections: mechanical, drill, placement, routing, mask/paste, silkscreen, fab notes, production files, BOM.
  - Sample values: mounting holes ≥3.3 mm, with screw head ≥40 mil larger than the hole; drill tolerances ±3 mil PTH and ±2 mil NPTH; mask bridge 8 mil (5 mil minimum); ≥3 fiducials.
  - This is the "Sierra Circuits layout checklist" I could not get in the first pass.
- **SCD** Sierra DFA checklist (2026-04-08) [P] — [ProtoExpress DFA](https://www.protoexpress.com/blog/pcb-design-for-assembly-checklist-important-checks-for-layout-engineers/).
  - Passive spacing table.
  - Part-to-hole ≥8 mil; part-to-annular-ring ≥7 mil.
  - Mask dam ≥4 mil; 1.6 mil mask clearance.
  - Silk ≥4 mil line and 25 mil text height.
  - Fiducials 40–118 mil, 118 mil from the edge, 3 global + 2 local.
  - Test-point distance L = 0.29·H + 0.7 mm.
  - Panel: 0.2" gaps, 118 mil from tabs.
- **SCR** Sierra "How to Perform PCB Design Review and Layout Clean-Up" (2022-10-06): separate via per ground/voltage pin; copper-to-edge ≥10 mil; via-to-via ≥6 mil; mask dam ≥5 mil; silk 25 mil/4 mil; part-to-edge ≥125 mil; production-data verification list — [ProtoExpress](https://www.protoexpress.com/blog/how-to-perform-pcb-design-review-and-layout-clean-up/) [P].
- **PP** PCB Power "PCB Design Review Checklist" PDF: sections on data package, drill, copper, mask/legend, mechanical and special layers, with "critical" items described as "the most common causes of production holds, rejections, and respins at PCB Power" — [PCB Power PDF](https://www.pcbpower.com/static/base/images/resources/DFM_Checklist.pdf) [P].
- **MF** MacroFab: "Five Tips to Clean Up Your Layout" — use the CM's DRC continuously, check silk from both sides, a test point on every node — [MacroFab](https://macrofab.com/blog/five-tips-to-clean-up-your-layout/) [P]. **MF2** pre-order checklist: SOT-23 pinouts commonly flipped, bottom-view drawings, no airwires, unique BOM designators, nothing outside the border in Gerbers — [MacroFab pre-order](https://www.macrofab.com/blog/pre-order-checklist-for-prototypes-eliminating-the-fear-of-a-bad-board) [P].
- **SF** SparkFun manufacturing rules: 10 mil traces typical, 6 mil absolute minimum; 8 mil spacing; 0603+ passives; parts on 0.005"/0.05" grid, headers on 0.1"; route from pad centers; pour isolation 12 mil; version code on bottom copper; labels on straight lines; autorouter only for prototypes — [SparkFun](https://learn.sparkfun.com/tutorials/how-to-sell-your-widget-on-sparkfun/designing-for-sparkfun-manufacture) [P]. **SFC** community checklist (colinb 2011): "Every time I make an error, I add an item to the checklist" — [SparkFun forum](https://community.sparkfun.com/t/pcb-design-tips-and-tricks/21883) [P].
- **UW** UWARG "PCB Layout Review Checklists" (v. 2026-03-08):
  - Per-IC section reviews; JLCPCB DFM via rules + clean DRC.
  - Decaps smallest→largest; copper balancing (<2× between pads for ≤0805); no traces under inductors without a GND plane between; ≥1 mm between small and tall parts; 0.5 mm mounting-hole clearance.
  - No polygon angles <45°; GND vias around high-speed vias.
  - Test points with net-name silk; a test point and an LED per rail.
  
  Source: [UWARG via Confluence REST](https://uwarg-docs.atlassian.net/wiki/spaces/EL/pages/2173501609) [P].
- **WAT** UW Rocketry review gates — [Confluence](https://uwaterloo.atlassian.net/wiki/spaces/ROCKETRY/pages/43024155641/Design+Reviews) [P]. **VSE** — [VSE](https://www.vse.com/blog/a-pcb-layout-checklist-for-error-free-manufacturing/) [P].
- **NASA** GSFC-STD-8001A (approved 2026-08-24): IPC-2221 Class 3 plus sectional standards; coupons; evaluation of non-standard features; drawing-note baseline; master drawing reviews for risk classes A/B; "A design review of the complete circuit board assembly should precede the PCB assembly process" — [GSFC-STD-8001A](https://standards.nasa.gov/system/files/tmp/GSFC-STD-8001A_Approved.pdf) [P].
- **TI-HS** SPRAAR7J "High-Speed Interface Layout Guidelines" (rev. Feb 2023): solid GND reference; not referenced to power planes; ≥1.5 W from voids; ≥90 mil from plane edge; stitching caps ≤1 µF across splits; no test points on high-speed pairs; via stubs <15 mil or back-drill; ~30 mil antipads; equal via counts; SMDs ≤0603; ESD/EMI rules — [TI SPRAAR7](https://www.ti.com/lit/pdf/spraar7) [P].
- **TI-EMI** SZZA009 — [TI](https://www.ti.com/lit/pdf/szza009) [P]. **TI-BUCK** SLYT614 — [TI](https://www.ti.com/lit/pdf/slyt614) [P]. **TI-1229** AN-1229 — [TI](https://www.ti.com/lit/pdf/snva054) [P]. **TI-FJ3** SLVAFJ3 — [TI](https://www.ti.com/lit/pdf/slvafj3) [P]. **TI** datasheet layout sections — [TPS61178](https://ti.com/document-viewer/TPS61178/datasheet/layout-guidelines-slvsda71918), [TPS55330](https://www.ti.com/document-viewer/TPS55330/datasheet/layout-guidelines-slvsbx81345) [P].
- **BO** Olney 2012 and **BOH** Olney 2024 — links above [P]. **ICD** — [PDF](https://www.icd.com.au/articles/Interactive_Place_&_Route_PCBDesign-Dec2012.pdf) [P].
- **FD** Feranec forum and workshop [P] (links above). **KF** KiCad forum [P]. **KG** KiCad Getting Started [P]. **MIT** [P].
- **FL** Flux "Common PCB Design Mistakes" (2026-04-16) — [Flux](https://www.flux.ai/p/blog/pcb-design-mistakes) [P]. **FX** Flux review process (IPC-2221C for spacing; state the IPC-6012F class) — [Flux](https://www.flux.ai/p/blog/pcb-design-review-process) [P]. **FXG** Flux grounding (splits only for audio/precision <100 kHz) — [Flux](https://www.flux.ai/p/blog/pcb-grounding-techniques) [P].
- **AP** AllPCB: prototypes "typically starting at 4-5 mils"; annular rings "must exceed 3 mils" — [AllPCB](https://www.allpcb.com/allelectrohub/the-ultimate-checklist-for-error-free-pcb-prototyping-from-schematic-to-fabrication) [P]. **BP** bestpcbs: run DFM "before quotation, before prototype release, before production release, and whenever the board changes material, layer count, package density, or assembly method" — [bestpcbs](https://www.bestpcbs.com/blog/2026/07/pcb-design-for-manufacturability-checklist/) [P].
- **AT** AtlasPCB (vendor, 2026-06-28): hold distribution and copper-balance threshold — [AtlasPCB](https://atlaspcb.com/blog/pcb-dfm-check-pre-order-verification) [P] (vendor self-report).
- **AD** Adom "kicad-board-audit" LLM skill (audit order, silenced-rule check, net-class coverage) — [Adom](https://wiki.adom.inc/adom/kicad-board-audit/files/SKILL.md) [P]. **KH** aklofas/kicad-happy (MIT; PCB analyzer methodology: decap-within-10 mm heuristic, tombstone copper ratio, layer-transition analysis, trace-proximity grid) — [methodology_pcb.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_pcb.md) [P]. **CE** claude-eda (unsourced thresholds) — [PLACEMENT-STRATEGY.md](https://github.com/l3wi/claude-eda/blob/main/templates/claude/skills/eda-pcb/reference/PLACEMENT-STRATEGY.md) [P].
- **CD** Cadence "PCB Layout Review Checklist": clearance for IC extraction tools; mounting-hole isolation; single-point analog/digital commons — [Cadence](https://resources.pcb.cadence.com/blog/2023-pcb-design-and-risk-benefit-analysis-in-component-placement) [S] (JS-rendered). **Tanner** personal JLC ordering checklist: check IC/diode orientation in the PCBA preview; keep option parts from being auto-matched; "Update this list as fails occurs" — [petertanner.dev](https://www.petertanner.dev/posts/PCB-manufacturing-checklist/) [P].
- **Other keys used in the table:**
  - **HT** Hartley — [Altium](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley), [ProtoExpress](https://www.protoexpress.com/blog/rick-hartley-pcb-design-recommendations-to-minimize-emi/) [P].
  - **NX** NextPCB — [NextPCB](https://www.nextpcb.com/blog/how-many-layers-can-a-pcb-have) [P].
  - **JR** JLCPCB routing rules — [JLCPCB](https://jlcpcb.com/blog/pcb-routing-rules-best-practices) [P].
  - **JP** JLCPCB placement guide — [JLCPCB](https://jlcpcb.com/blog/pcb-component-placement-guide-2026) [P].
  - **EN** electronics-notes — [electronics-notes](https://www.electronics-notes.com/articles/analogue_circuits/pcb-design/pcb-layout-routing.php) [P].
  - **PC** PCD&F 2019 — [PCD&F](https://www.qgdigitalpublishing.com/article/PCB+Guided+Insights/3388181/589425/article.html) [P].
  - **BG** bestpcbs ground-plane guide — [bestpcbs](https://www.bestpcbs.com/blog/2026/09/circuit-board-ground-plane-layout/) [S].
  - **FXP** Flux placement tutorial — [Flux docs](https://docs.flux.ai/tutorials/component-placement) [S] (JS-rendered).
  - **PS** ProtoExpress stack-up guide — [ProtoExpress](https://www.protoexpress.com/pcb-design-guides/pcb-stack-up-design-guide/) [S] (lamination-cycle claim not found on the current page).
- Not public or not found: NCAB's checklist is behind a form, but its section titles are visible (component packaging, placement, mechanical, routing, power design, DRC, silkscreen, Gerber review) — [NCAB](https://www.ncabgroup.com/pcb-design-checklist) [P]. Other gaps:
  - Oxide: the public RFD API lists 84 public RFDs with none on PCB review — [Oxide RFD API](https://rfd-api.shared.oxide.computer/rfd) [P].
  - Antmicro publishes an open-hardware portal and KiCad/Blender flow, not a checklist — [Antmicro](https://antmicro.com/blog/2023/04/open-hardware-portal) [P].
  - Adafruit: no checklist found [S].
  - "Ajay Bhargav": not found [S].
  - ADI: analog.com unreachable.

**Legend.**
- Severity: **C** = critical (dead or unsafe board, unmanufacturable, unassemblable → respin); **M** = major (SI/PI/EMC/thermal/yield/reliability risk); **m** = minor (debug, documentation, cosmetics).
- Automation: **A** = geometry/DRC only (KiCad check or custom-rule constraint named where applicable); **S** = semi-automatic (needs net classes, part roles or datasheet parameters, then computable); **J** = judgment, external info or simulation.
- Source keys are as listed above. Numeric thresholds are the cited sources' values. They are fab-specific and differ between sources (e.g., minimum silk height of 25 mil per Sierra vs 1.0 mm per PCB Power vs 50 mil per UWARG), so treat them as parameters.

#### Master checklist table

| ID | Category | What to check | Why | Sev | Auto | Sources |
|---|---|---|---|---|---|---|
| PRC-01 | Process | Schematic review signed off before layout; pin/gate swaps made during layout back-annotated and re-reviewed | Layout of an unreviewed or out-of-sync schematic carries its errors forward | C | S (parity auto; sign-off J) | AZ, VSE, WAT |
| PRC-02 | Process | Board/schematic parity: no missing/extra/duplicate footprints, pad nets match schematic, footprint attributes match symbol ("update PCB from schematic") | LVS | C | A (DRC: Missing/Extra/Duplicate footprint; Pad net doesn't match schematic; attributes mismatch) | HH, JN, KD, AL |
| PRC-03 | Process | Zero unrouted connections / airwires; no polygon breaks | Open nets ("not unusual for a PCB to be sent to manufacturing without all the parts placed and routed") | C | A (DRC: Missing connection between items) | HH, JN, KD, VSE, MF2, AL |
| PRC-04 | Process | DRC 100% clean; every exclusion/waiver inspected and signed off | Waivers hide defects | C | A (+J for waivers) | AZ, GD, KD |
| PRC-05 | Process | Rules (track/space, drill, annular ring, mask web, silk width, edge clearance) set from fab/assembler capability before layout and kept current; use the CM's own DRC rule file | DRC is only meaningful against real fab limits; reviewers then only confirm rules + clean DRC | C | S (set) → A (check) | GD, PK, UW, MF, SF, VSE |
| PRC-06 | Process | Layout checked against functional and non-DFM requirements (connector locations, heights, creepage, test access, thermal limits, isolation zones, keepouts) | DRC passes functionally wrong designs | M | J | AL3, ALP, AL6 |
| PRC-07 | Process | Each significant IC circuit (regulators, LDOs, MCUs, transceivers, level shifters) reviewed against its datasheet/EVM layout guidance, ideally by a separate reviewer | IC-specific constraints live in datasheets | M | J (LLM extraction → S) | UW, JN, WAT, TI-BUCK, SC |
| PRC-08 | Process | Staged reviews: pre-layout, placement, critical routing, final/DFM | Each review isolates one error class while it is cheap to fix | M | J | VSE, FX |
| PRC-09 | Process | Review tied to a version-controlled, locked baseline; design decisions documented; change log per revision | Avoid reviewing or building stale data | m | J | WAT, HH, AL6 |
| PRC-10 | Process | All parts available in the chosen package; no NRND/EOL parts; alternates identified for critical parts | A late package change forces re-layout | M | S | AZ, GD, MF2, AL6, SC |
| PRC-11 | Process | BOM, netlist and schematic synchronized | "One of the most common errors seen during a PCB design review" | M | A (parity) + S (BOM) | ALP, SC |
| PRC-12 | Process | ERC/DRC severity overrides, exclusions and "ignore" settings audited before trusting a clean result | "Anything on 'ignore' makes a clean pass hollow" | C | A (read project rule severities) | AD |
| PRC-13 | Process | DRC violations grouped by root cause (one bad footprint, keepout flag or via style) before fixing | Hundreds of violations often collapse to a few causes | m | S | AD |
| PRC-14 | Process | Non-standard features (outside IPC-2220/6010 series) identified, evaluated and approved before final design | Hi-rel risk control | M | J | NASA |
| PRC-15 | Process | Each suspected issue verified against a primary source (datasheet, vendor checklist, EVB) before it is reported or fixed | Avoid false positives and wrong fixes | M | J | AD, UW |
| PRC-16 | Process | Compliance evidence (RoHS/REACH/UL) attached to parts; compliance sign-off at milestones | Compliance as a gate | m | J | AL6 |
| PRC-17 | Process | Checklist updated after every escaped error | Organizational learning loop | m | J | SFC, AZ, Tanner |
| PRC-18 | Process | Three formal review points: after schematic, after rough placement (before routing), after completion | Large layout changes are easiest before routing | M | J | WAT, VSE, BO |
| DFM-01 | DFM | Features don't push fab limits unnecessarily (SparkFun: 10 mil traces typical, 8 when needed, 6 absolute minimum; Robertson: "not always force the manufacturer to the limits") | Yield, cost | M | A (margin-to-limit report) | AZ, GD, AP, SF, BO |
| DFM-02 | DFM | Annular ring ≥ fab/IPC-class minimum (PK: 5 mil Class 2 / 7 mil Class 3 for 10 mil vias; AP: >3 mil) | Drill breakout | C | A (annular_width) | PK, AP, KD, PP, ALP |
| DFM-03 | DFM | Hole-to-hole and hole-to-copper clearances (inner and outer layers) | Breakout, shorts | C | A (hole_clearance, hole_to_hole) | KD, BP, PP, ALP |
| DFM-04 | DFM | Copper-to-edge clearance (Sierra ≥10 mil; SparkFun 8 mil) unless edge plating or edge-launch is confirmed and noted | Exposed copper, router wear | M | A (edge_clearance) | GD, AZ, KD, BP, SCR, SF, PP |
| DFM-05 | DFM | Via aspect ratio and microvia stack rules within capability | Plating reliability | M | A (microvia_aspect_ratio, microvia_stack_depth) | PK, KD, ALP |
| DFM-06 | DFM | Few unique drill sizes (combine sizes within 0.05 mm) | Faster, cheaper fab | m | A | PK, PP, SCR, ALP |
| DFM-07 | DFM | Mask dams between fine-pitch pads; no mask aperture bridging different nets | Solder bridges | M | A (bridged_mask) | BP, KD, ALP |
| DFM-08 | DFM | No copper slivers or too-narrow necks (PCB Power: ≥8 mil spacing between pads in planes) | Flaking, opens | m | A (Copper sliver; connection_width) | KD, PP |
| DFM-09 | DFM | Copper balanced per layer pair; stackup and copper weights symmetric; plane layers symmetric; inner-layer venting/thieving | Warpage, delamination | m | S | BP, PP, SCR |
| DFM-10 | DFM | Outline closed and valid; internal corners millable; external corners rounded | Unmillable shapes | M | A (Board has malformed outline) | HH, KD, PK |
| DFM-11 | DFM | PTH finished hole ≥ lead + ~0.2 mm (≥10 mil); square pins sized by diagonal; plating allowance; pad ≥ hole + 10–15 mil; through-holes that get soldered are plated | Parts won't insert; weak joints | C | S (needs lead dimensions) | GD, JN, HH, AL |
| DFM-12 | DFM | Via tenting/plugging policy decided and consistent; untented vias kept away from pads | Solder theft vs test access | m | A | GD, JN, UW |
| DFM-13 | DFM | Surface finish specified (e.g., ENIG for flatness/fine pitch) and compatible with fine-pitch pads and edge contacts | Solderability, coplanarity | M | J | AZ, PK, ALP |
| DFM-14 | DFM | Board size fits standard panels efficiently | Cost | m | J | PK |
| DFM-15 | DFM | Margins chosen for production volume ("10-50 boards doesn't mean you can 1000") | Tolerance stack-up | M | J | GD |
| DFM-16 | DFM | Feature sizes compatible with copper weight (heavier copper needs larger spacing; e.g., 8 mil at 2 oz) and inner-layer etch compensation | Etch capability | M | A (per-layer rules) + S | ALP, SC, JR, PP |
| DFM-17 | DFM | Precision holes (press-fit, alignment pins) carry tighter diameter and position tolerances | Standard tolerances are insufficient | M | J | ALP |
| DFM-18 | DFM | Layer-registration margin on small pads, antipads and plane clearances | Registration errors | M | S | ALP |
| DFM-19 | DFM | Slots, cutouts and castellations defined as routed outlines with achievable radii; no slots made from chained/overlapping drills | Tooling, rejects | M | A | ALP, PP |
| DFM-20 | DFM | Via-in-pad fill/cap/planarization specified and compatible with via geometry and outer-layer features (BGA VIP noted in fab notes) | Process compatibility | M | S | ALP, SC |
| DFM-21 | DFM | No overlapping or co-located drills; PTH and NPTH in separate or clearly marked tools | Broken bits, barrel voids, process mix-ups | C | A (DRC: Drilled holes co-located / too close) | PP, KD |
| DFM-22 | DFM | NPTH free of unused copper pads; NPTH on the contour treated as part of the outline; edge PTH noted | DRC false positives, edge errors | m | A | PP |
| DFM-23 | DFM | Drill chart has a distinct symbol per size; tolerances stated (Sierra: ±3 mil PTH / ±2 mil NPTH); drill values in whole numbers | Fab interpretation | m | A | SC, SCR, PP |
| DFM-24 | DFM | Via-to-via spacing ≥ fab minimum (Sierra 6 mil); pad fully covers hole | Breakout | M | A | SCR, KD |
| DFM-25 | DFM | HDI: dielectric thickness, stacked vs staggered microvias, laser-via annular rings, separate clearances for laser vs mechanical vias | HDI reliability | M | A (microvia rules) | ALP, KD |
| DFM-26 | DFM | Mask openings and dams meet fab spec (PCB Power: opening ≥0.06 mm, dam ≥0.08 mm; Sierra DFA: dam ≥4 mil, openings 1:1, ≥1.6 mil pad-to-mask); wider for non-green masks | Bridging, mask on pads | M | A (solder_mask_expansion, bridged_mask) | PP, SCD, SCR |
| DFM-27 | DFM | Copper fill of symmetric layer pairs within ~20% (15% for double-sided reflow) — vendor threshold | Warpage | m | A | AT |
| STK-01 | Stackup | Stackup (materials, dielectric thicknesses, copper weights, finished thickness) verified with the fab | Impedance and manufacturability depend on real materials | C | J | AZ, AL, FD, HT, ALP |
| STK-02 | Stackup | Every signal layer one dielectric from a solid reference plane; continuous ground within one layer of every signal trace; no unshielded adjacent signal layers | Field containment, return path | M | S (layer roles) | HT, PK, BOH, AL, SCR |
| STK-03 | Stackup | Controlled-impedance nets, targets and reference layers listed in fab notes | Fab tunes widths | M | S | AZ, PK, SC |
| STK-04 | Stackup | Impedance calcs include solder mask (or mask removed over RF) | Mask shifts Z | M | S | AZ, PK |
| STK-05 | Stackup | Controlled-impedance traces use the computed width/gap for their layer (per-layer net-class rules) | Mismatch → reflections | M | A (once classes are defined) | PK, HH, AL, SC |
| STK-06 | Stackup | Layer count is the minimum giving continuous references, power copper and escape; +2 layers if channel use >70%; validated by test route | Cost vs SI/routability | M | J (S estimate) | NX, VSE |
| STK-07 | Stackup | Sequential lamination cycles limited | Yield, cost | m | S | PS ([S]) |
| STK-08 | Stackup | High-speed signals reference GND planes, not power planes | Return quality ("TI does not recommend high-speed signal references to power planes") | M | S | TI-HS |
| STK-09 | Stackup | Every controlled-impedance net matches a net-class pattern (nets matching none silently get Default, e.g., USB D+/D−) | Silent impedance miss | C | A (class-coverage report) | AD |
| STK-10 | Stackup | Room for impedance/test coupons; coupons per IPC-2221 on production panels for hi-rel | Fab verification | m | J | ALP, NASA, AL |
| STK-11 | Stackup | Hi-rel: design to IPC-2221 Class 3 plus the sectional standard (2222/2223/2226/2228) | Mission reliability | M | J | NASA |
| STK-12 | Stackup | Stack-up drawing (layer order, materials, thicknesses, impedance table) in the mechanical layer / fab drawing; impedance written as "Layer N: Z ±tol, referenced to Layer M" | Ambiguous stackup is the top hold cause in one vendor's data | C | J | PP, SC, AT |
| MEC-01 | Mechanical | Outline, dimensions and mounting holes match the enclosure (checked in 3D with accurate models, including mechanical parts) | Board doesn't fit | C | S (MCAD) | AZ, AL, CE, VSE |
| MEC-02 | Mechanical | Mounting holes have clearance/keepout for screw head and washer | Shorts, crushed parts | M | A (keepout) | AZ, AL, HH |
| MEC-03 | Mechanical | Mounting holes deliberately plated+grounded (with stitching) or isolated | EMC/safety | M | S | AZ, PK, HH, CD |
| MEC-04 | Mechanical | Off-board connectors match the mating standard (orientation, keying, pin 1, FPC top/bottom contact); pinout reversed if connectors face each other | Mis-mating | C | J | AZ, JN, UW, SFC |
| MEC-05 | Mechanical | Clearance for mating plug/cable and latch access; connector courtyard covers the larger mating part; mating 3D model placed | Can't plug/unplug | M | S (3D) | AZ, GD, SC, UW |
| MEC-06 | Mechanical | UI elements on the outward-facing side, logically arranged | Usability | M | J | AZ, HH |
| MEC-07 | Mechanical | Component heights within the enclosure; heatsink/fan clearance | Collisions | M | S (3D) | AZ, HH, VSE |
| MEC-08 | Mechanical | No part collisions or courtyard overlaps (3D body check, nothing under other parts) | Unassemblable | C | A (Courtyards overlap) | AZ, KG, KD, UW, SCR |
| MEC-09 | Mechanical | Perimeter keepouts (card guides, conveyor border ~3 mm, mouse bites) respected | Handling, depaneling | M | A (rule area) | AZ, GD |
| MEC-10 | Mechanical | MLCCs/stress-sensitive parts away from V-scores, tabs and mounting holes, oriented against flex; soft termination for >1210 | Cracked caps | M | S | AZ, PK, SCD |
| MEC-11 | Mechanical | Connectors mechanically anchored (THT posts/hybrid), especially RF and frequently mated | Pad lift | M | J | PK, GD |
| MEC-12 | Mechanical | Edge/right-angle connectors at the edge with correct overhang; edge fingers per spec | Fit | M | S | GD, HH |
| MEC-13 | Mechanical | Tool access: IC extraction, sockets, programming fixtures, screwdrivers, probes | Serviceability | m | S | HH, CD |
| MEC-14 | Mechanical | Connectors/mounting holes on a coarse grid; round board dimensions (SparkFun: frame on 0.1" grid starting at 0,0) | MCAD, drawings | m | A | GD, SF |
| MEC-15 | Mechanical | Board thickness (and local thickness at card-edge connectors) specified and matching connectors/enclosure | "You'd be surprised how often this is overlooked" | C | J | AL3, ALP |
| MEC-16 | Mechanical | Keep-out outline follows board shape; slots/cutouts used as barriers stop nets crossing milled areas | Cut traces | M | A | AL |
| MEC-17 | Mechanical | Board-to-board connectors spaced and located for mating (stack height, alignment) | Mating | C | S (3D) | UW |
| MEC-18 | Mechanical | UI conventions (e.g., potentiometers increase clockwise) | Usability | m | J | AL |
| MEC-19 | Mechanical | Mounting holes ≥3.3 mm by default with antipads; screw head ≥40 mil larger than hole; ≥0.5 mm copper/part clearance | Fastener fit | M | A | SC, SCR, UW |
| MEC-20 | Mechanical | House-standard connector pinouts and orientation conventions reused across boards (e.g., SparkFun I2C GND, VCC, SDA, SCL) | Interoperability | m | S | SF, JN |
| MEC-21 | Mechanical | Part-to-edge distance meets assembler/handling needs (Sierra ≥125 mil; Flux ≥5 mm near panel edges) | Depanel damage | M | A | SCR, FL, SCD |
| PLC-01 | Placement | Order: fixed parts → main ICs (CPU/memory) → other ICs → power → small passives | Fixed items constrain the rest | M | J (process) | FD, GD, JP, CE |
| PLC-02 | Placement | Grouped by functional block; power/analog/digital/RF separated; each IC's private parts gathered around it | Short routes, contained noise | M | S (sheet/role) | FXP, GD, KG, KF, SCD, BO |
| PLC-03 | Placement | Switching converters away from sensitive analog | Noise | M | S | GD, AZ |
| PLC-04 | Placement | Temperature-sensitive parts away from hot parts; small parts not next to high-dissipation parts | Lifetime, drift | M | S | HH, JN, SCR |
| PLC-05 | Placement | Interface ICs, ESD and filters next to their connectors | Short exposed path | M | S | HH, CE, SC |
| PLC-06 | Placement | Series/damping resistors at the source; terminations at the load | Termination works only at the correct end | M | S | HH, JN, AL, SC |
| PLC-07 | Placement | Crystal/oscillator next to its IC with short traces and ground guard (CE default ≤5 mm) | Jitter, EMI | M | S | HH, JN, CE, AL |
| PLC-08 | Placement | ADC anti-alias filters close to the ADC input | Pickup after the filter | M | S | GD, HH |
| PLC-09 | Placement | All components placed before routing | Inserting parts later is very hard | M | J (process) | FD, MIT, VSE |
| PLC-10 | Placement | Ratsnest length and crossings minimized; short high-speed lengths prioritized | Routability proxy | M | A | KG, KF, AL, BO |
| PLC-11 | Placement | Routability trial: quick autoroute ≥85% completion before committing | Placement and layer-count problems surface early | M | A | BO, VSE |
| PLC-12 | Placement | Routing channels between dense ICs (memories, BGAs) | Escape room | M | S | FD, BO |
| PLC-13 | Placement | Rework: any part replaceable without removing others; tweezer/iron access | Repairability | m | S | JN, GD, ICD, AL |
| PLC-14 | Placement | No routing under noisy/sensitive parts or under inductors (unless a GND plane is between); no vias under metal-film resistors | Coupling | m | S | HH, GD, UW, AL, SCR |
| PLC-15 | Placement | Polarized/like parts in one orientation or a repeatable pattern | Human/AOI inspection | m | A | GD, JN, HH, BO |
| PLC-16 | Placement | Footprints on a regular grid (Olney: 100 mil large, 25 mil chips; SparkFun 0.05"; Pikafu 5 mil origin grid) | Neatness, MCAD | m | A | GD, PK, BO, SF |
| PLC-17 | Placement | Tall parts don't shadow small parts for AOI; SMD ≥2–5 mm from THT joints if selective soldering | Inspection/soldering | m | S | GD |
| PLC-18 | Placement | Nearby inductors oriented/spaced to limit magnetic coupling | Crosstalk | m | S | CE (unsourced) |
| PLC-19 | Placement | Heat sources placed for airflow/edge; copper for spreading | Thermal | M | S | CE, JN, VSE |
| PLC-20 | Placement | Bottom-side lands aligned with top-side lands to open via space | Via channels | m | S | BO |
| PLC-21 | Placement | Parts placed by cross-probing from the schematic by function and importance | Placement reflects function | M | J (process) | BO |
| PLC-22 | Placement | Pre-placement fit check (autoplace or area estimate) that everything fits the outline | Detect impossible boards early | M | A | BO, KF |
| PLC-23 | Placement | Small chip parts not adjacent to tall or high-thermal-mass parts (UWARG ≥1 mm) | Shadowing, soldering, rework | m | A/S | AL, UW, SCR |
| PLC-24 | Placement | No unrelated components within 1 inch of a microcontroller crystal (TI EMI guideline) | "Most EMI-related crosstalk problems center around the crystal" | M | S | TI-EMI |
| PLC-25 | Placement | Circuits with similar supply/ground domains grouped together | PDN, isolation | m | S | SCD |
| PLC-26 | Placement | Pin 1 of all ICs in the same orientation where function allows; repeated parts in a clear matrix | Inspection, assembly | m | A | BO |
| PLC-27 | Placement | Power-stage order: IC → input cap (placed and routed immediately, no vias) → inductor/catch diode → output cap → small-signal parts → single-point ground and vias | The hot loop dominates converter behavior | C | J/S | TI-BUCK, TI-1229 |
| PDN-01 | Power integrity | Decoupling caps as close as possible to power pins, one per pin (Altium: under 15 mm; CE default <3 mm) | Loop inductance | M (C for fast ICs) | S (cap-to-pin association) | AZ, JN, KG, CE, AL, UW, SCR |
| PDN-02 | Power integrity | Smallest-value cap closest to the pin | HF effectiveness | M | S | PK, TI, UW, FD |
| PDN-03 | Power integrity | Low-inductance mounting (via-in-pad if available, else short side vias to plane) | Mounting inductance dominates | M | S | AZ, HH |
| PDN-04 | Power integrity | Bulk capacitance at power entry and regulator outputs | LF stability | M | S | HH, CE |
| PDN-05 | Power integrity | Every IC power/ground pin connected (pour/thermal connections on all layers; ground pins have vias to the plane) | Floating supply pins | C | A (parity + connectivity) | GD, HH, AL |
| PDN-06 | Power integrity | Trace/plane widths sized for current and temperature rise | Burn-out, IR drop | C | S (per-net current) | AZ, HH, JN, GD, SC |
| PDN-07 | Power integrity | Vias sized and multiplied on high-current paths | Fusing, IR drop | M | S | GD, HH, AL |
| PDN-08 | Power integrity | Plane slots from via antipads minimized | Slotted planes break returns | M | S | AZ |
| PDN-09 | Power integrity | Power filtered at board entry | Conducted noise | M | S | GD |
| PDN-10 | Power integrity | DNP footprints for extra regulator input/output caps | Bring-up tuning | m | J | PK |
| PDN-11 | Power integrity | Every GND/VCC pin and every decap has its own via(s); vias not shared | Shared vias add inductance | M | S | AL, BO, SCR |
| PDN-12 | Power integrity | Enough GND current-carrying vias near connectors and current sinks/sources | Return current capacity | M | S | AL |
| PDN-13 | Power integrity | Width calculated for every track carrying >100 mA; internal-layer width used if airflow is poor (Flux: ~10 mil/A on 1 oz external at 10 °C rise as a rough start; internal ~2×) | Overheating | C | S | AL, FL |
| PDN-14 | Power integrity | Through-hole pin rows in planes keep copper webs between pins (no merged-antipad slots) | Plane slots | M | A | TI-EMI, AZ |
| PDN-15 | Power integrity | BGA decap staging: nF at pins, µF nearby/around BGA, 100s of µF around BGA or on the path from the source | Frequency-staged decoupling | M | S | FD |
| PWR-01 | Power conversion | Switching hot loop (input cap–switch–rectifier; boost: switch–rectifier–output cap) has minimal area | High di/dt loop radiates | C | S + J/sim | TI, GD, TI-BUCK |
| PWR-02 | Power conversion | SW-node copper area minimal; ground plane under the regulator | dV/dt antenna | M | S | TI |
| PWR-03 | Power conversion | FB network at the FB pin; FB trace away from SW/inductor | Regulation noise | M | S | TI |
| PWR-04 | Power conversion | Current-sense lines Kelvin-routed apart from power planes (net ties); gate-drive return routed with its gate | Accuracy, ringing | M | S | TI-FJ3 |
| PWR-05 | Power conversion | AGND/PGND separated and joined at a single point per datasheet | Ground noise into the controller | M | S/J | TI-FJ3, TI-BUCK |
| PWR-06 | Power conversion | Tracks between switch, inductor and caps (including GND) short and wide | Loss, EMI | M | S | GD |
| PWR-07 | Power conversion | Connectors and regulators current-rated in the chosen package | Overheating | C | J | AZ |
| PWR-08 | Power conversion | Shorten before widening: reduce power-loop length first; "beefing up" traces is a last resort | Inductance tracks length | M | S | TI-1229 |
| PWR-09 | Power conversion | Thermal vias under power ICs / exposed pads | Junction temperature | M | S | TI-FJ3 |
| GND-01 | Ground/return | At least one continuous, unbroken ground plane | Return path, EMI | M | S | AL, FL, SCR |
| GND-02 | Ground/return | High-speed nets don't cross splits/slots/voids; if unavoidable, stitching caps (TI: ≤1 µF, at the crossing) or vias | Detoured return acts as an antenna | C (HS) | S | AZ, HH, HT, BOH, TI-HS, FL, VSE, SC |
| GND-03 | Ground/return | Return/stitching vias next to signal vias at reference-layer changes; GND vias around high-speed vias | Return continuity | M | S | PK, BOH, BG, UW, FL |
| GND-04 | Ground/return | Ground not split without justification (audio/precision <~100 kHz exception) | Splits usually worsen EMI | M | J | GD, HT, FXG, FL |
| GND-05 | Ground/return | If grounds are separated, they join at exactly one point | Ground loops | M | S | HH, JN, CD, AL |
| GND-06 | Ground/return | No plane bottlenecks or isolated/floating copper | Starved returns; antennas | M | A (Isolated copper fill) | GD, JN, KD, UW, SCR |
| GND-07 | Ground/return | Vias spread evenly across planes (no via walls) | Avoid slots | m | S | JN |
| GND-08 | Ground/return | No signals, especially noisy ones, along board edges; edge ground ring/stitching | Edge radiation ("Never run noisy traces on the outside edge") | m | A | HH, GD, TI-EMI, FL |
| GND-09 | Ground/return | Return path checked for every critical net | Root of many SI/EMI problems | M | S/J | GD, HT |
| GND-10 | Ground/return | High-speed traces ≥1.5×W from reference voids and ≥90 mil from plane edges (TI) | Fringing/return disruption | M | A/S | TI-HS |
| GND-11 | Ground/return | Two-layer boards: no ground loops; ground track sized for each device's return; unbroken pour under every high-speed trace; power and ground run over each other; length:width ≤3:1 | 2-layer return control | M | S | AL, TI-EMI |
| GND-12 | Ground/return | No buried signal traces in the ground plane (use the +V plane if unavoidable) | Plane integrity | M | A | TI-EMI |
| GND-13 | Ground/return | No loops in power and ground nets | Loop antennas | M | S | SCR, AL |
| HS-01 | High-speed | Differential pairs coupled at impedance gap, as close as possible; uncoupled length limited | Mode conversion | C | A (diff_pair_gap, diff_pair_uncoupled) | AZ, HH, KD, AL, VSE |
| HS-02 | High-speed | Intra-pair skew matched (serpentines at the mismatched end) | Mode conversion | M | A (skew) | AZ, JN, KD, TI-HS |
| HS-03 | High-speed | Inter-signal length matching per interface (DDR, PCIe, Ethernet, LVDS, HDMI, USB3+, MIPI) | Timing | M | A (length/skew rules) | AZ, JR, AL |
| HS-04 | High-speed | Clearance to aggressors; pair-to-pair spacing maximized; clocks isolated | Crosstalk | M | S | AZ, GD, TI-HS, VSE, SC |
| HS-05 | High-speed | Stubs and layer changes minimized; via count limited | Reflections | M | A/S (via_count) | HH, AZ, KD, SC, SCR, FL |
| HS-06 | High-speed | Terminations present and at the correct end | Reflections | M | S | HH, JN, AL |
| HS-07 | High-speed | Mitered/curved bends on impedance-sensitive traces (Flux: a 90° corner on a 20.5 mil trace is transparent below ~25 GHz, so this is mostly DFM/aesthetic) | Minor discontinuity | m | A (track_angle) | HH, JN, FL, SF |
| HS-08 | High-speed | Wide connector/SMD pads compensated (plane cutouts/voids under pads) | Impedance dip | M | J/sim | AZ, TI-HS |
| HS-09 | High-speed | Footprint option for a common-mode filter on off-board high-speed pairs | EMC fallback | m | J | HH, TI-HS |
| HS-10 | High-speed | Series-R / 0 Ω placeholders on fast single-ended lines | Edge control later | m | J | HH, PK |
| HS-11 | High-speed | Critical nets routed first, by hand, and locked (power/ground and susceptible nets → clocked data → rest; autorouter only for <50 kHz nets) | Everything else routes around them | M | J (process) | JR, EN, PC, BO, TI-EMI |
| HS-12 | High-speed | "Low-frequency" buses judged by edge rate | Fast edges radiate | m | J | GD |
| HS-13 | High-speed | Impedance constant along each trace, including across layer changes and after BGA escape | Reflections | M | S | AL, TI-HS |
| HS-14 | High-speed | Electrically long nets (Altium: longer than 1/6 of rise time) simulated and terminated; long parallel runs simulated for crosstalk | SI | M | J/sim | AL |
| HS-15 | High-speed | No test points or stubs on high-speed differential nets; no stubs to test points or unused connector pins | Stubs, discontinuities | M | A/S | TI-HS, AL, SCR |
| HS-16 | High-speed | High-speed traces not under/near crystals, oscillators, SMPS, mounting holes, magnetics or clock-duplicating ICs | Coupling | M | S | TI-HS |
| HS-17 | High-speed | Via stubs <15 mil or back-drilled; antipads enlarged (~30 mil) on high-speed vias; no non-functional pads | Resonance, capacitance | M | A/S | TI-HS, SC |
| HS-18 | High-speed | Equal via count on both members of a pair, symmetric and close to the SoC | Mode conversion | M | A | TI-HS |
| HS-19 | High-speed | Pair routed symmetrically; deviations (escape, connector) short; breakout within 0.25" of the package; constant width after escape | Skew, Z | M | S | TI-HS |
| HS-20 | High-speed | Series SMDs on high-speed lines ≤0603 (prefer 0402), placed symmetrically | Pad discontinuity | M | S | TI-HS |
| HS-21 | High-speed | Routing topology per interface checked (point-to-point, fly-by, T, daisy chain); signal groups use the same topology | Timing/SI | M | S | SC, FD |
| HS-22 | High-speed | Net-length vs Manhattan/MST ratio outliers flagged ("no scenic routes") | Delay, EMI | m | A | AL, BO |
| HS-23 | High-speed | Trace length vs wavelength: >λ/10 (FCC) or >λ/50 (automotive/consumer 2-layer) considered for termination | Antenna factor | m | S | TI-EMI |
| HS-24 | High-speed | Adjacent signal layers routed orthogonally (H/V) | Broadside coupling | m | A/S | VSE, SC |
| RF-01 | RF | RF line (e.g., GCPW) impedance verified with the real stackup; mask effect | Mismatch | M | S | AZ, PK |
| RF-02 | RF | Via-fence pitch ≤ λ/8 | Leakage | M | S (needs frequency) | PK, HH |
| RF-03 | RF | Stitching vias in large top-layer ground pads (e.g., SMA) | Resonances | M | S | AZ |
| RF-04 | RF | Antenna/module keep-outs per datasheet | Detuning | C | A once drawn; S to derive | GD, JN, CE |
| RF-05 | RF | Shield-can footprint where needed | EMC fallback | m | J | HH, AL |
| RF-06 | RF | Edge launch: fab confirmed for copper to edge | Launch performance | M | J | AZ |
| ANA-01 | Analog | Guard rings/cages where needed | Leakage, pickup | M | J | AZ |
| ANA-02 | Analog | Sensitive analog separated from SMPS/noisy digital; filters between groups | Noise | M | S | AZ, GD, KG, SCR, SC |
| ANA-03 | Analog | Noisy traces not adjacent to critical traces on any layer | Crosstalk | M | S | GD |
| ANA-04 | Analog | MLCC microphonics considered | Noise | m | J | AZ |
| EMC-01 | EMC/ESD | ESD/TVS at the connector entry with a short ground path | Shunt the surge early | M | S | HH, CE, TI-HS, SC |
| EMC-02 | EMC/ESD | No small or sharp floating copper | Radiation | m | A (Isolated copper fill) | JN, KD |
| EMC-03 | EMC/ESD | Ferrite-bead DC-current margin; filter targets defined | Bead impedance collapses under bias | m | J | HH |
| EMC-04 | EMC/ESD | SMPS snubber footprint option | Ringing | m | J | HH, TI-1229 |
| EMC-05 | EMC/ESD | Plane keepouts and chassis bonding for shielded connectors and magnetics | Isolation | M | S | AZ, HH |
| EMC-06 | EMC/ESD | EMI/RFI filtering at the exit point (board edge, connector, shield) | Filter before leaving | M | S | AL |
| EMC-07 | EMC/ESD | ESD pads in series with the track (the surge reaches the protection pad before the protected device); unprotected traces kept away from protected ones | Protection effectiveness | M | S | AL, TI-HS |
| EMC-08 | EMC/ESD | High-speed ESD layout: AC caps on the protected side of the CMF, all close to the connector; ~60% voids under ESD pads; 0402 0 Ω CMF no-stuff | Loss and protection | m | S | TI-HS |
| EMC-09 | EMC/ESD | Decoupling at connectors where needed; separate ESD earth paths considered | EMC | m | J | AL |
| EMC-10 | EMC/ESD | Board-to-board cables: ≥1 ground return per 9 signals (1 per 4 if >1 ft) | Return path in cables | m | S | TI-EMI |
| THM-01 | Thermal | Thermal reliefs on plane connections for solderability/rework (except heat-sinking or high-current pads) | Cold joints | M | A (zone_connection) | AZ, GD, PK, JN, UW, PP |
| THM-02 | Thermal | Solid connections plus thermal-via arrays under dissipating pads; copper area for regulators, SMPS, LED drivers, FETs, motor drivers, CPUs, PAs | Junction temperature | M | S | AZ, JN, HH, AL, SCR |
| THM-03 | Thermal | Thermal balance on 2-terminal chips (UWARG: copper on one pad <2× the other for ≤0805; KH heuristic: copper ratio <0.3 high risk) | Tombstoning | M | S | AZ, GD, UW, KH |
| THM-04 | Thermal | Thermal lands unmasked; exposed pads on the correct net | Heat transfer, function | M | S | JN, HH, SCD |
| THM-05 | Thermal | Thermal-relief spokes fully resolved | Weak connection | M | A (min_resolved_spokes) | KD |
| THM-06 | Thermal | Relief geometry within fab spec (PCB Power: 10 mil gap, 8 mil spoke) | Solderability | m | A (thermal_relief_gap, thermal_spoke_width) | PP |
| FP-01 | Footprints | Footprint matches the ordered package (e.g., not 0805 for 0603); symbol pinout matches the package | Unassemblable / wrong pins | C | S | AZ, FL, SFC |
| FP-02 | Footprints | Pinout drawings read in the correct view (top vs bottom) | Mirrored pinout | C | J | AZ, HH, MF2 |
| FP-03 | Footprints | 1:1 printout checked against physical parts | Dimension errors | M | J | AZ, GD, JN, SFC |
| FP-04 | Footprints | 3D models present and verified | Valid MCAD checks | M | S | AZ, AL |
| FP-05 | Footprints | Mask apertures on all SMT lands and PTH pads | Unsolderable pads | C | A | AZ, PP, SC, SFC |
| FP-06 | Footprints | SMD vs NSMD pad definition (BGA) confirmed | Joint reliability | M | S | AZ, GD |
| FP-07 | Footprints | New/vendor footprints checked against the latest datasheet land pattern | Vendor libraries are often wrong | M | J | JN, HH, FL, VSE, SCD |
| FP-08 | Footprints | Courtyard present and valid; footprint matches library copy and symbol filters | Overlap checks rely on courtyards | m | A | KD |
| FP-09 | Footprints | No vias embedded in footprints | Via consolidation | m | A | PK |
| FP-10 | Footprints | Exposed/thermal pads present; assembly note if the pad is the only GND connection | Function | M | S | HH |
| FP-11 | Footprints | SMT pad length ≥ lead + ~8 mil | Fillet | M | S | JN |
| FP-12 | Footprints | SOT-23 transistor/MOSFET pinouts verified (N vs P, NPN vs PNP; G/S/D, B/C/E) | "Common error is getting SOT-23 … pinouts flipped" | C | S | MF2, SFC |
| FP-13 | Footprints | Courtyard reflects the real body where it extends beyond the pads | Pick-and-place collisions | M | S | ALP |
| RTE-01 | Routing | No acute trace angles | Acid traps | m | A (track_angle) | HH, KD, UW |
| RTE-02 | Routing | Adjacent IC pins never bridged directly; traces leave pad ends (U-shape) | Looks like a short | m | A/S | GD, HH, JN |
| RTE-03 | Routing | No dangling tracks/vias, wandering traces or antennas | Stubs | m | A (Track has unconnected end; via_dangling) | GD, KD, VSE, SCR |
| RTE-04 | Routing | Traces off the outline and depanel zones | Damage | m | A (edge_clearance) | GD |
| RTE-05 | Routing | Superfluous vias removed | Reliability, cost | m | A | HH |
| RTE-06 | Routing | Teardrops where stress is expected (MacroFab: prevent neck-down) | Cracks | m | A | AZ, MF |
| RTE-07 | Routing | Unconstrained traces generously wide | Yield | m | A | GD |
| RTE-08 | Routing | No routing between/under fine-pitch (QFP/QFN/BGA) pads unless planned | Bridging, inspection | m | S | SCR |
| RTE-09 | Routing | Tracks enter/exit pads at the pad center ("route from pads") | Solderability | m | A | SF |
| RTE-10 | Routing | Critical/tuned routes locked after completion | Accidental edits | m | A | BO |
| RTE-11 | Routing | Final per-net visual sanity pass (highlight each net) | Catches odd routes | m | J | BO |
| ZON-01 | Zones | Zones refilled after the last edit and before CAM; pours enabled; none shelved | Stale fills | C | A | AZ, GD, UW, AL |
| ZON-02 | Zones | No pour between adjacent IC pins | Inspection confusion | m | S | HH |
| ZON-03 | Zones | Zone priorities correct; no unintended intersections; same-net overlaps merged | Unexpected shorts/voids | M | A (Copper zones intersect) | KD, UW |
| ZON-04 | Zones | Planes as solid filled contours (not hatch-painted); small pads flashed. Note: PCB Power warns hatch planes cause lamination microvoids, while jnoss recommends hatched pours — sources conflict | CAM, lamination | M | A | PP, JN |
| ZON-05 | Zones | Pour isolation larger than track clearance (SparkFun: 12 mil) | Pour creeping onto traces | m | A | SF |
| ZON-06 | Zones | No polygon angles <45° | Slivers, acid traps | m | A | UW |
| ZON-07 | Zones | Leftover auto-generated zones, dangling stubs and single-layer vias removed | Junk copper | m | A | AD |
| PST-01 | Paste/mask | No untented/unfilled vias in pads (except low-power QFNs) | Solder wicking, voids | C | A | AZ, GD |
| PST-02 | Paste/mask | Paste on large exposed pads segmented (~70% area unless the datasheet says otherwise) | Float, voids | M | A (solder_paste_rel_margin) | AZ, PK, GD, SC |
| PST-03 | Paste/mask | Small pads 100% aperture; large pads reduced | Solder volume | m | A | AZ |
| PST-04 | Paste/mask | No paste on edge fingers, test points, fiducials or DNP parts | Contamination | M | A/S | AZ, GD |
| PST-05 | Paste/mask | Mask clearance around pads (~50 µm typical; Sierra 1.6 mil) | Mask on pad / bridging | m | A (solder_mask_expansion) | AZ, SCD |
| ASM-01 | Assembly | Fiducials: ≥3 global (asymmetric), on both sides if double-sided, 2 local diagonal at fine pitch; 40–118 mil diameter, ~118 mil from edge, with clearance | Machine vision | M | A/S | AZ, AL, GD, FD, SCD, SC |
| ASM-02 | Assembly | Pin-1/polarity marks present and visible after assembly (not under the part) | Orientation errors | M | S | GD, JN, HH, AL, PP, SC |
| ASM-03 | Assembly | BOM and pick-and-place consistent with the board (DNP/DNI marked, centroid rotation convention checked) | Assembly errors | M | S | GD, SC |
| ASM-04 | Assembly | No unnecessarily tiny parts (SparkFun: 0603+ passives) | Yield, hand soldering | m | J | GD, SF |
| ASM-05 | Assembly | Plastic connectors rated for reflow | Melting | m | J | GD |
| ASM-06 | Assembly | Layer-number markers in copper | Layer-order errors | m | A | AZ, PP |
| ASM-07 | Assembly | Assembly order feasible | Buildability | m | J | HH |
| ASM-08 | Assembly | Footprints accept alternate packages/dual footprints for swap-prone parts | Supply chain | m | J | GD, AL6 |
| ASM-09 | Assembly | Passive part-to-part spacing per assembler table (Sierra: 0402 S=12 mil, 0603 21 mil, 0805 30 mil) | Pick-and-place, rework | M | A (courtyard_clearance) | SCD, VSE |
| ASM-10 | Assembly | Component-to-hole wall ≥8 mil (50–100 mil for manual soldering); component-to-annular-ring ≥7 mil | Soldering | m | A | SCD |
| ASM-11 | Assembly | Rework/inspection access: 80 mil for rework tools; 60° inspection angle (rule of thumb: spacing = tallest neighbor's height) | Inspection | m | S | BO, ICD, AL |
| ASM-12 | Assembly | Assembly drawing: top/bottom instructions, outlines matching pick-and-place, ESD/heatsink/connector handling notes | Assembly intent | M | S | SCD, SC |
| ASM-13 | Assembly | IC/diode orientation checked in the assembler's placement preview; option/DNP parts not auto-matched by the assembler's catalog | Common PCBA ordering mistake | C | J | Tanner |
| DFT-01 | Test/debug | Test points on power rails and critical signals; hidden nets made accessible | Bring-up | M | S | GD, HH, PK, AL, UW, VSE |
| DFT-02 | Test/debug | GND test/hook points next to critical test points | Short probe ground loops | m | S | GD, HH, PK, UW |
| DFT-03 | Test/debug | Probe clearance; test pads away from edge (JN: not within 5 mm) for fixturing | Fixture access | m | A | AZ, JN, AL |
| DFT-04 | Test/debug | Programming/debug headers, jumpers and reset accessible | Development | M | J | GD, HH, JN, AL |
| DFT-05 | Test/debug | Status LEDs (UWARG: one per power rail, optional per bus line) | Debug | m | J | JN, PK, UW |
| DFT-06 | Test/debug | Software-readable board-revision straps | Field support | m | J | HH |
| DFT-07 | Test/debug | 0 Ω links to isolate sections; DNP pull options | Staged bring-up | m | J | GD, PK |
| DFT-08 | Test/debug | Caps oriented with power nets facing the same way | Probe shorts | m | S | PK |
| DFT-09 | Test/debug | Test-point distance from components by height (Sierra: L = 0.29·H + 0.7 mm; UWARG ≥1 mm) | Probe access | m | S | SCD, UW |
| DFT-10 | Test/debug | Test-point silk shows the net name; test points on bus lines and enable/shutdown/reset nets | Bring-up | m | S | UW |
| DFT-11 | Test/debug | Test points on one side (bottom for bed-of-nails, top for manual probing) | Fixturing | m | A | AL |
| DFT-12 | Test/debug | No test points under BGAs; ≥5.08 mm between adjacent BGAs for test-point access | Probe access | m | A | SCD |
| DFT-13 | Test/debug | Test point on every node where feasible; dedicated pad ≥1 mm | Testability | m | S | MF |
| SLK-01 | Silkscreen | No silk on pads, drills, vias or exposed copper; silk clipped by mask flagged; silk outside component bodies | Contaminates joints | M | A (silk_clearance; clipped by mask) | AZ, GD, JN, KD, UW, MF, SFC |
| SLK-02 | Silkscreen | Text height/thickness within fab limits (Sierra 25 mil / 4 mil; PCB Power ≥1.0 mm; UWARG 50 mil; PK ≥0.1") | Legibility | m | A (text_height, text_thickness) | AZ, KD, PK, SCD, PP, UW |
| SLK-03 | Silkscreen | Designators near their parts, unambiguous, in at most 2 orientations; no overlaps | Readability | m | A | HH, JN, GD, AL, SCD, MF |
| SLK-04 | Silkscreen | Bottom-side text mirrored | Readability | m | A (Mirrored/non-mirrored text checks) | AZ, KD, PP |
| SLK-05 | Silkscreen | Revision, date, name; blank box for serial/assembly revision; version code revised every spin | Traceability | m | S | AZ, HH, JN, GD, SF, AL, MF2 |
| SLK-06 | Silkscreen | Labels for connector pinouts/signal names, test points, LEDs, switches and states, jumpers, fuse rating, functional groups | Usability | m | S | HH, JN, AZ, SF, SC, UW |
| SLK-07 | Silkscreen | Tick marks every 5/10 pins; corner pins numbered | Probing | m | S | HH, JN |
| SLK-08 | Silkscreen | Silk removed (not crammed) in dense areas | Ambiguity | m | J | AZ |
| SLK-09 | Silkscreen | Designators annotated geographically | Finding parts | m | A | HH, JN |
| SLK-10 | Silkscreen | Connector overhang marked beyond the edge | Assembly | m | S | GD |
| SLK-11 | Silkscreen | Product markings: logos, copyright, warning/hazard labels, QA/test block with barcode | Compliance, traceability | m | J | AL, SCR |
| SLK-12 | Silkscreen | Legend clearances per fab (PCB Power: ≥8 mil to copper, ≥0.25 mm to routed edge / 0.45 mm to scored edge; Sierra: 4.5 mil silk-to-mask) | Clipping | m | A | PP, SCD |
| SLK-13 | Silkscreen | Labels aligned on straight lines; uniform text size | Visual quality | m | A | SF, SC |
| SLK-14 | Silkscreen | Silk checked from both sides | Mirroring/numbering errors | m | J | MF |
| HV-01 | HV/safety | Creepage and clearance by voltage, including between layers (IPC-2221C tables) | Arcing | C | A (creepage, clearance by net class) | GD, HH, KD, AL, FX |
| HV-02 | HV/safety | Isolation barriers adequately sized | Safety | C | S | HH |
| HV-03 | HV/safety | Signal and power not in the same connector; connectors for different purposes not interchangeable | Mis-mating fire (Fermilab 1987) | M | J | HH |
| CAM-01 | Outputs | DRC and zone fill re-run immediately before export | Stale outputs | C | A | AZ |
| CAM-02 | Outputs | Gerber and drill exported together and inspected in an independent viewer | Misalignment | M | S/J | AZ, PK, PP, SFC |
| CAM-03 | Outputs | Uploaded files are the latest and complete (right layer count, geometry exported correctly) | "Yes, this does happen" | C | S | HH, SC |
| CAM-04 | Outputs | Fab drawing/notes: dimensions, datums, drill table, stackup table, impedance table, IPC class, finish, mask/silk colors, minimum drill and annular ring, blind/buried/via-fill notes | Fab intent | M | J | PK, FX, SC, SCR, PP |
| CAM-05 | Outputs | Assembly drawing: paste type, staking, hole sizes | Assembly intent | m | J | PK |
| CAM-06 | Outputs | Gerber X2; drill format stated | Fewer CAM errors | m | A | GD |
| CAM-07 | Outputs | RS-274X/X2 (not RS-274D); Excellon with embedded tool list; 1:1 scale; consistent units and zero offset across Gerber and drill; no zero-size apertures | CAM errors, misalignment | C | A | PP |
| CAM-08 | Outputs | Readme/fab notes listing every file, a 24-h contact, intentional opens/shorts and special requirements; no CAD/Office files in the package | Fab communication | M | J | PP, SC |
| CAM-09 | Outputs | IPC-356 netlist (or ODB++ / IPC-2581) delivered for bare-board electrical test | Netlist compare at fab | M | A | SC |
| CAM-10 | Outputs | Unwanted tool-generated layers removed; outline on a layer sent to fab; mechanical layer has dimensions, reference hole, drill map, countersink details; keep-out layer separate from outline | Fab clarity | M | S | SC, SCR, AL, PP |
| CAM-11 | Outputs | Final Gerbers from the manufacturer approved before production, especially on re-orders after changes | Wrong revision built | M | J | SC |
| CAM-12 | Outputs | No title block or features outside the board border in Gerber/ODB++; BOM designators unique | Upload errors | m | A | MF2 |
| CAM-13 | Outputs | Drawing-note baseline addresses all critical requirements; master drawing reviewed (hi-rel) | Requirement flow-down | M | J | NASA |
| PNL-01 | Panel | Panelization specified (tabs vs V-score); rails ≥3 mm; stiffness | Handling | m | S | AZ, GD |
| PNL-02 | Panel | Panel-position markers | Process debug | m | A | AZ |
| PNL-03 | Panel | Tracks/parts clear of depanel zones (Sierra: ≥118 mil from tabs; no perforated tabs next to sensitive parts) | Damage | M | A | GD, AZ, SCD |
| PNL-04 | Panel | Frame area for conveyors and clamping; panel not too large for board thickness | Handling, bounce | m | S | AL |
| PNL-05 | Panel | Panel silkscreen (QA blanks, date, machine/company, barcode, PN/rev); panel fiducials and origin mark | Traceability | m | S | AL, SCD |
| PNL-06 | Panel | Boards in the same orientation; ≥0.2" gaps; no V-score where parts overhang edges | Depanel damage | m | A | SCD |
| PNL-07 | Panel | V-score/mill/tab layers present and aligned with the board | Fab | m | A | AL |
| PNL-08 | Panel | Test coupons on production panels (hi-rel) | Structural-integrity testing | m | J | NASA, AL |
| FLX-01 | Flex | Flex components oriented to minimize bending forces | Cracking | M | S | AZ |
| FLX-02 | Flex | Teardrops on wire-to-pad connections | Cracks | M | A | AZ |
| FLX-03 | Flex | Each flex region meets the allowed bend radius (static vs dynamic) for its construction | Cracking | C | S | ALP |
| FLX-04 | Flex | Traces cross bends perpendicular and curved with no sharp corners; no overlapping copper on adjacent flex layers (I-beaming) | Strain, stiffness | M | S | ALP |
| FLX-05 | Flex | Vias, plated holes, components and solder joints kept out of bend areas and away from rigid-flex transitions | Stress | C | A (rule areas) | ALP |
| FLX-06 | Flex | Coverlay openings allow for registration/adhesive flow; stiffeners match the mechanical function | Assembly | M | S | ALP |
| FLX-07 | Flex | Impedance continuity through rigid-to-flex transitions | SI | M | J/sim | ALP |


#### Coverage statistics (computed from the table above)
- Total distinct items: **299** across 24 categories: Process 18; DFM 27; Stackup 12; Mechanical 21; Placement 27; Power integrity 15; Power conversion 9; Ground/return 13; High-speed 24; RF 6; Analog 4; EMC/ESD 10; Thermal 6; Footprints 13; Routing 11; Zones 7; Paste/mask 5; Assembly 13; Test/debug 13; Silkscreen 14; HV/safety 3; Outputs 13; Panel 8; Flex 7.
- Severity: C = 41, M = 151, m = 107.
- Automation class (primary tag): A = 101, A/S = 9, S = 119, S/J = 4, J = 66 (A-dominant share ≈ 37%, S-dominant ≈ 41%, J ≈ 22%).
- Of the 41 Critical items: A = 19, A/S = 0, S = 14, S/J = 1, J = 7 — i.e. 83% of Critical items are at least semi-automatable.

### Inferences
- The single biggest enabler for automation is a **semantic annotation layer**: part roles, net roles, currents, voltages, frequencies and datasheet thresholds. KiCad 9+ component classes and net classes, plus custom-rule functions (`hasComponentClass()`, `inDiffPair()`, `intersectsCourtyard()`, `enclosedByArea()`, `fromTo()`, `getField()`), give most of the plumbing ([KiCad custom rules](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc) [P]).
- The new fab-side sources (PCB Power, Sierra, AtlasPCB) move many critical items into **output/documentation correctness**: file formats, unambiguous stackup and impedance notes, drill definitions. These are cheap to automate and are where fabs actually put orders on hold.
- Thresholds conflict between sources (silk height 25 mil vs 1.0 mm vs 50 mil; edge clearance 8 vs 10 mil; part-to-edge 125 mil vs 5 mm). A critic library must load thresholds from a **fab/assembler profile**, not hard-code them.

### Gaps
- Official JLCPCB and PCBWay DFM checklists, and MacroFab's capabilities PDF (403), were not retrieved. Only blog checklists were available.
- ADI layout checklists: analog.com unreachable.
- No NASA/JPL *layout-level* checklist was found. GSFC-STD-8001A covers design standards, reviews and coupons, not geometry checklists.
- NCAB's checklist is gated behind a form.

---

## Q5. Which layout mistakes most often cause respins, and is there frequency or severity data?

### Takeaway
There is no rigorous, public root-cause breakdown of PCB respins. Quantitative evidence falls into four kinds:
- (a) Analyst studies, usually seen via vendor citations: about **2.8–2.9 respins per project** (Lifecycle Insights, 2018), and Aberdeen 2010's **14.1 vs 3.8 prototypes** for non-integrated vs best-in-class flows.
- (b) An industry survey (PCD&F/Circuits Assembly, Sep 2025): **nearly 60% of designers produce 1–5 respins a year**.
- (c) A fab-industry estimate: only **<2–20% of designs reach manufacturing without technical queries**.
- (d) Vendor self-reports ranking DFM holds: stackup/impedance/fab-note ambiguity at the top, then drill-to-copper, annular ring, trace/space and mask dams.

Qualitative sources agree on footprint/pinout errors, decoupling and return-path errors, mechanical misfit, unrouted nets and stale outputs.

### Cited Findings
**Respin counts and costs**
- Lifecycle Insights (Chad Jackson) simulation-driven design study: "the average number of design respins is 2.9 per project, which amounts to approximately 16 days of unplanned development time and more than $82,000 in additional costs" — [PCD&F news, 2018](https://pcdandf.com/pcdesign/index.php/editorial/menu-news/design-news/13176-new-mentor-xpedition-pcb-design-platform-provides-upfront-multi-dimensional-verification) [P].
- The same study as relayed by Mentor: "58% of all new product design projects incur added costs and time delays"; respins average "8.5 days to complete at a cost of $44,000 (USD) per re-spin" — [Electronic Design interview](https://www.electronicdesign.com/industrial-automation/article/21807687/the-new-shiftleft-multidimensional-pcb-designverification-platform) [P].
- iCD dates it to "Lifecycle Insights (September 2018)", with "$28,482" per respin and $82,598 per product — [iCD](https://icd.com.au/Sim.html) [P].
- Altium cites the same firm as "2.8 board respins per project, each costing a staggering $46,000" — [Altium](https://resources.altium.com/p/fragmented-feedback-loops) [P].
- **These secondary citations conflict on per-respin cost** ($28.5k / $44k / $46k) and count (2.8 vs 2.9). The original report was not found, and every citation comes from a vendor marketing context.
- Aberdeen (Feb 2010) via Siemens: "PCB prototypes were found to represent 31% of the overall product cost … in a nonintegrated design flow … an average of 14.1 physical prototypes were required for a moderately complex PCB design … compared to … 3.8 prototypes" — [Siemens blog 2014](https://blogs.sw.siemens.com/electronic-systems-design/2014/02/27/less-is-more-fewer-prototypes-equals-more-savings/) [P]. The original press release returned 403 — [GlobeNewswire](https://www.globenewswire.com/news-release/2010/03/17/994060/0/en/PCBs-Are-a-Strategic-Asset-for-Cost-Reduction-and-Faster-Time-to-Market-New-Study-Finds.html) [S].
- PCD&F/Circuits Assembly salary survey (article dated 30 Sep 2025):
  - "Nearly 60% produce just 1–5 respins a year, and 81% say that hasn't increased in the past 12 to 18 months."
  - Respondents: 29% with >30 years' experience; 83% handle 4–6 layer boards; 55% HDI; 55% high-speed; 54% BGAs.
  
  Source: [Circuits Assembly](https://www.circuitsassembly.com/ca/editorial/menu-features/42616-among-pcb-design-raises-are-up-benefits-are-down-and-deadlines-don-t-budge.html) [P]. An earlier edition reportedly gave 55% (1–5), 17% (6–10) and 9.5% (11–15) [S].

**DFM/fabrication-hold data**
- Dana Korf (I-Connect007, 2019-11-14): "less than 2–20% of the designs transfer to manufacturing perfectly without any deviation requests or TQs", and "Often, 25–50% of a PCB fabricator's front-end engineering capacity" goes to pre-release DFM reviews (an expert estimate, not a survey) — [Dana on Data](https://design.iconnect007.media/article/120585/dana-on-data-the-dfmdata-transfer-process-is-broken/120588/design) [P].
- AtlasPCB (vendor, 2026-06-28), "across 10,000+ orders processed in the last 12 months", ranks causes of fabrication holds:
  - missing or ambiguous stackup specification: 28%;
  - undefined impedance requirements: 22%;
  - drill-to-copper violations: 18%;
  - incomplete fab notes: 15%;
  - BGA annular-ring violations: 12%.
  
  It also claims "95% of holds are preventable with a 15-minute pre-submission check" — [AtlasPCB](https://atlaspcb.com/blog/pcb-dfm-check-pre-order-verification) [P]. Vendor self-report; methodology unpublished.
- A dev.to vendor post (2026-07-02) says that of ~200 designs/month reviewed, "Over 60% have at least one DFM issue". Its ranked failure rates are trace/space 45%, annular ring 38%, drill-to-copper 32%, mask dam 28%, acid traps 22%, copper balance 20%, outline-to-copper 18%, via aspect ratio 15%, silk over pad 12%, thermal relief 10%, panel tabs 8% and impedance feasibility 8% — [dev.to](https://dev.to/abc_8b09c7009ee0029b85665/pcb-dfm-check-12-point-verification-before-ordering-with-failure-rates-from-200-monthly-reviews-1n9f) [P]. Anonymous vendor marketing, low confidence. The two vendor rankings disagree, which is expected given different populations.
- PCB Power marks its ⚠ items as "the most common causes of production holds, rejections, and respins at PCB Power" — [PCB Power PDF](https://www.pcbpower.com/static/base/images/resources/DFM_Checklist.pdf) [P]. Its ⚠ items include:
  - RS-274X format; separate PTH/NPTH; 1:1 scale; consistent units and offsets;
  - Gerber viewed before submission;
  - top text right-reading;
  - no overlapping drills or slots made from chained drills;
  - drill-to-pad registration; annular rings;
  - trace/space; copper away from edge; no slivers;
  - stackup drawing; symmetric copper;
  - mask openings and dams; no mask over SMD pads;
  - legend height; legend off pads; polarity markers;
  - outline/cutouts and PTH/NPTH designation.

**Qualitative causes**
- Sierra DFA: "Defects such as tombstoning, solder bridging, component misalignment, and wrong polarity markings are among the most common challenges faced during assembly" — [ProtoExpress DFA](https://www.protoexpress.com/blog/pcb-design-for-assembly-checklist-important-checks-for-layout-engineers/) [P].
- Flux: "Most PCB design mistakes come from poor component placement, incorrect routing, and weak grounding". Return-path errors are "the source of a disproportionate share of EMI failures" — [Flux mistakes (2026-04-16)](https://www.flux.ai/p/blog/pcb-design-mistakes) [P].
- MacroFab: "Common error is getting SOT-23 transistor and MOSFET package pinouts flipped around"; "Some manufacturers draw the mechanical layout of the part from the bottom" — [MacroFab pre-order](https://www.macrofab.com/blog/pre-order-checklist-for-prototypes-eliminating-the-fear-of-a-bad-board) [P].
- VSE: "it is not unusual for a PCB to be sent to manufacturing without all the parts placed and routed"; "Many board designs have been ruined because the schematic still contained preliminary library parts" — [VSE](https://www.vse.com/blog/a-pcb-layout-checklist-for-error-free-manufacturing/) [P].
- Adom's audit skill: "Never trust a clean ERC". Its examples: power_out/bidirectional pins floating ("MCU VCAP pins with no capacitors. Board dead, ERC green"), mistyped power pins, and a controlled-impedance net matching no class pattern ("classic: USB D+/D−") — [Adom](https://wiki.adom.inc/adom/kicad-board-audit/files/SKILL.md) [P].
- Failure-log checklists: azonenberg ("school of hard knocks") — [README](https://github.com/azonenberg/pcb-checklist) [P]; SparkFun's colinb ("Every time I make an error, I add an item") — [SparkFun forum](https://community.sparkfun.com/t/pcb-design-tips-and-tricks/21883) [P]; Tanner ("Update this list as fails occurs") — [Tanner](https://www.petertanner.dev/posts/PCB-manufacturing-checklist/) [P]; henrikh ("Has the correct/latest files been uploaded? Yes, this does happen") — [henrikh](https://github.com/henrikh/pcb-checklist) [P].
- Vendor claims of "up to 60% of prototype failures from design errors including footprints" were found only in uncited blog snippets [S] and are not reported as findings.

#### Consensus ranking (proxy, not frequency)
Number of independent sources (of the keys in the table) that flag each item. This measures agreement among checklist authors, **not** measured failure frequency. Caveat: keys from the same publisher (SC/SCD/SCR from Sierra; AL/ALP/AL3/AL6 from Altium; MF/MF2; BO/BOH; the TI-* notes) are counted separately, which inflates their items. Top 25 by source count, then severity:

| Rank | ID | Item (abridged) | Sev | # sources | Sources |
|---|---|---|---|---|---|
| 1 | GND-02 | High-speed nets don't cross splits/slots/voids; if unavoidable, stitching caps (TI: ≤1 µF, at the crossing)... | C (HS) | 8 | AZ, HH, HT, BOH, TI-HS, FL, VSE, SC |
| 2 | DFM-04 | Copper-to-edge clearance (Sierra ≥10 mil; SparkFun 8 mil) unless edge plating or edge-launch is confirmed a... | M | 7 | GD, AZ, KD, BP, SCR, SF, PP |
| 3 | PDN-01 | Decoupling caps as close as possible to power pins, one per pin (Altium: under 15 mm; CE default <3 mm) | M (C for fast ICs) | 7 | AZ, JN, KG, CE, AL, UW, SCR |
| 4 | SLK-01 | No silk on pads, drills, vias or exposed copper; silk clipped by mask flagged; silk outside component bodies | M | 7 | AZ, GD, JN, KD, UW, MF, SFC |
| 5 | SLK-05 | Revision, date, name; blank box for serial/assembly revision; version code revised every spin | m | 7 | AZ, HH, JN, GD, SF, AL, MF2 |
| 6 | PRC-03 | Zero unrouted connections / airwires; no polygon breaks | C | 6 | HH, JN, KD, VSE, MF2, AL |
| 7 | PRC-05 | Rules (track/space, drill, annular ring, mask web, silk width, edge clearance) set from fab/assembler capab... | C | 6 | GD, PK, UW, MF, SF, VSE |
| 8 | ASM-01 | Fiducials: ≥3 global (asymmetric), on both sides if double-sided, 2 local diagonal at fine pitch; 40–118 mi... | M | 6 | AZ, AL, GD, FD, SCD, SC |
| 9 | ASM-02 | Pin-1/polarity marks present and visible after assembly (not under the part) | M | 6 | GD, JN, HH, AL, PP, SC |
| 10 | DFT-01 | Test points on power rails and critical signals; hidden nets made accessible | M | 6 | GD, HH, PK, AL, UW, VSE |
| 11 | HS-05 | Stubs and layer changes minimized; via count limited | M | 6 | HH, AZ, KD, SC, SCR, FL |
| 12 | PLC-02 | Grouped by functional block; power/analog/digital/RF separated; each IC's private parts gathered around it | M | 6 | FXP, GD, KG, KF, SCD, BO |
| 13 | THM-01 | Thermal reliefs on plane connections for solderability/rework (except heat-sinking or high-current pads) | M | 6 | AZ, GD, PK, JN, UW, PP |
| 14 | SLK-02 | Text height/thickness within fab limits (Sierra 25 mil / 4 mil; PCB Power ≥1.0 mm; UWARG 50 mil; PK ≥0.1") | m | 6 | AZ, KD, PK, SCD, PP, UW |
| 15 | SLK-03 | Designators near their parts, unambiguous, in at most 2 orientations; no overlaps | m | 6 | HH, JN, GD, AL, SCD, MF |
| 16 | SLK-06 | Labels for connector pinouts/signal names, test points, LEDs, switches and states, jumpers, fuse rating, fu... | m | 6 | HH, JN, AZ, SF, SC, UW |
| 17 | DFM-02 | Annular ring ≥ fab/IPC-class minimum (PK: 5 mil Class 2 / 7 mil Class 3 for 10 mil vias; AP: >3 mil) | C | 5 | PK, AP, KD, PP, ALP |
| 18 | HS-01 | Differential pairs coupled at impedance gap, as close as possible; uncoupled length limited | C | 5 | AZ, HH, KD, AL, VSE |
| 19 | HV-01 | Creepage and clearance by voltage, including between layers (IPC-2221C tables) | C | 5 | GD, HH, KD, AL, FX |
| 20 | MEC-08 | No part collisions or courtyard overlaps (3D body check, nothing under other parts) | C | 5 | AZ, KG, KD, UW, SCR |
| 21 | PDN-06 | Trace/plane widths sized for current and temperature rise | C | 5 | AZ, HH, JN, GD, SC |
| 22 | STK-01 | Stackup (materials, dielectric thicknesses, copper weights, finished thickness) verified with the fab | C | 5 | AZ, AL, FD, HT, ALP |
| 23 | ANA-02 | Sensitive analog separated from SMPS/noisy digital; filters between groups | M | 5 | AZ, GD, KG, SCR, SC |
| 24 | CAM-04 | Fab drawing/notes: dimensions, datums, drill table, stackup table, impedance table, IPC class, finish, mask... | M | 5 | PK, FX, SC, SCR, PP |
| 25 | DFM-01 | Features don't push fab limits unnecessarily (SparkFun: 10 mil traces typical, 8 when needed, 6 absolute mi... | M | 5 | AZ, GD, AP, SF, BO |

### Inferences
- Combining the vendor hold data (stackup/impedance/fab-note ambiguity first) with the consensus ranking (ground continuity, current capacity, fab-matched rules, stackup verification, decoupling, fiducials, silk on pads) suggests critic priority should be **documentation and specification completeness, then geometry rules, then physics**.
- Survey numbers (≈60% of designers at 1–5 respins/year; 2.9 respins/project) mean even experienced designers respin routinely. An automated critic stack that catches documentation and footprint/pinout errors pre-fab targets the cheapest and most common failures.

### Gaps
- The original Lifecycle Insights 2018 report and the original Aberdeen 2010 report were not retrieved.
- No independent, peer-reviewed root-cause distribution of PCB respins exists in the sources found.
- Pass-rate claims (AtlasPCB "38% first-pass") appear only in a snippet [S].

---

## Q6. How do experts evaluate a layout visually ("it looks right"), and can it be quantified?

### Takeaway
"Looks right" means concrete regularities:
- like parts in one orientation, pin-1s aligned, memories in a matrix;
- parts and labels on grids and straight lines; text in at most two directions; geographic designators;
- compact power loops; tight, ordered decoupling;
- short, uncrossed airwires; traces leaving pad ends at pad centers;
- identical channel layouts.

Olney: "if a PCB design looks good, it will probably work well", but neat long parallel routing creates crosstalk, so aesthetics must not override physics. Flux shows 90° corners are not an SI issue below tens of GHz, so bend style is mostly aesthetic/DFM. All of these heuristics can become metrics.

### Cited Findings
- Olney: "Similar types of components should be aligned on the board in the same orientation"; "orient pin 1 on all IC components the same"; memory chips "in a clearly defined matrix with pin 1 orientation in the same direction"; grid 100 mil for large parts / 25 mil for chips; "if a PCB design looks good, it will probably work well. However, neatness in routing often leads to unwanted crosstalk" — [Olney 2012](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design) [P].
- SparkFun: board frame on a 0.1" grid at (0,0); "All parts are placed on a 0.005" grid. If possible, use a .05" grid"; headers on a 0.1" grid; "Route with straight lines and 45 degree corners only … T-intersections are okay"; "Traces should enter and exit center of pad"; "Makes sure labels are on a straight line" — [SparkFun](https://learn.sparkfun.com/tutorials/how-to-sell-your-widget-on-sparkfun/designing-for-sparkfun-manufacture) [P].
- grosdode: polarized parts "in the same direction or in a repeatable pattern"; coarse grid; easy board dimensions; consistent text orientation — [grosdode](https://github.com/grosdode/PCB-design/blob/main/PCB_Checklist/pcb_checklist.md) [P]. jnoss: polarized parts the same way; legend in one or two directions; designators left-right/top-bottom; traces exit pad ends — [jnoss](https://github.com/jnoss/pcb-checklist) [P]. henrikh: consistent orientation; text from at most two directions; references ordered by layout — [henrikh](https://github.com/henrikh/pcb-checklist) [P]. Pikafu: origin grid 5 mil; vias on a 5 mil grid; cap power nets facing the same way — [Pikafu](https://github.com/Pikafu/pcb_design) [P].
- Altium (Harris): "All designators are only in one or two orientations"; "Each designator is close to and clearly identifies the associated component" — [Altium](https://resources.altium.com/p/pcb-design-and-review-checklist) [P].
- Flux: with a −15 dB return-loss criterion, "a 20.5 mil wide trace is transparent below 25 GHz … For the vast majority of digital designs, 90° corners are not a signal integrity crisis"; the reasons to prefer 45° are practical — [Flux mistakes](https://www.flux.ai/p/blog/pcb-design-mistakes) [P].
- Airwire minimization — [KiCad Getting Started](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/getting_started_in_kicad/getting_started_in_kicad.adoc) [P]; [Autodesk](https://www.autodesk.com/products/eagle/blog/pcb-layout-basics-component-placement/) [S]. Fewest crossings between groups (Rerouter) — [KiCad forum](https://forum.kicad.info/t/strategy-to-use-for-placing-components/23682) [P].
- Olney's net-highlight sanity check: nets "longer than the Manhattan length or spiral around the board" [P] (link above).
- Existing metric implementations in LLM tooling (kicad-happy): decap proximity (C within 10 mm of a U, sharing a net, same side); tombstoning copper ratio min/max (<0.3 high, 0.3–0.6 medium); trace-proximity grid for coupling length; per-net layer-transition analysis for return paths — [kicad-happy methodology_pcb.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_pcb.md) [P]. These thresholds are tool heuristics, not standards.
- KiCad supports regularity directly: Align/Distribute tools and multichannel Repeat Layout — [KiCad editing](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc) [P]; [KiCad multichannel](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_multichannel.adoc) [P].

### Inferences (proposed quantifications; not from a published source)
| Heuristic (source) | Metric | Computation (KiCad board + netlist) |
|---|---|---|
| Consistent orientation (GD, JN, HH, BO) | Orientation entropy per part class | H = −Σ p(θ) log p(θ) over {0, 90, 180, 270} for same-footprint parts within a block; for polarized parts, the fraction pointing in the modal direction |
| Pin-1 alignment (BO) | Pin-1 direction agreement | Fraction of ICs whose pin-1 vector matches the board modal direction |
| Grid alignment (GD, PK, SF, BO) | Grid-snap ratio | Fraction of footprint origins on grid g (25/50/100 mil or 1/1.27 mm) within ε; separately for vias and headers (0.1") |
| Rows/columns (KiCad align tools, SF labels) | Collinearity score | Clusters of equal x or y centers among same-class parts or labels |
| Minimal, uncrossed airwires (KG, KF) | HPWL + crossing count | Half-perimeter or MST wirelength per net; pairwise MST-edge crossings |
| No scenic routes (BO, AL) | Manhattan ratio | Routed length ÷ Manhattan (or MST) length per net; flag outliers |
| Compact power loops (FD, TI) | Hot-loop area; SW-node area | Polygon area through role-tagged loop pads; SW-net copper area |
| Decap tightness and order (AZ, PK, FD, UW) | Distance and rank order | Cap-pad to IC-pin path length; Spearman correlation of value vs distance |
| Text orientation (HH, JN, AL) | Distinct text-direction count | Number of readable directions (target ≤2); bottom text mirrored |
| Geographic designators (HH, JN) | Rank correlation | Spearman correlation of designator number vs row-major position per prefix |
| Pad-exit style (JN, GD, SF) | Side-exit / off-center count | Track endpoints not at the pad center or attaching on the long side between same-net adjacent pins |
| Neatness vs crosstalk (BO) | Parallel-run length | Coupled length between non-pair nets on the same or adjacent layers (kicad-happy grid method) |
| Channel symmetry (KiCad multichannel) | Layout congruence | RMS pose deviation of target vs reference channels after the isomorphism map |
| Signal flow (Pikafu, HH) | Flow monotonicity | Fraction of inter-block edges pointing "forward" along an axis from input to output connectors |

- Olney's caveat argues for pairing every neatness term with a **coupling-penalty term**, so the optimizer doesn't create long parallel runs to look tidy.

### Gaps
- No empirical study links layout aesthetics to measured SI/EMC performance or reviewer acceptance. Metric weights need calibration against expert-rated boards.

---

## Implications for an LLM-driven KiCad placer/router

### Takeaway
Encode the expert workflow as a **backtracking state machine** with three human-style review gates, matching UW Rocketry and VSE practice:
1. After schematic and constraints.
2. After placement, before routing. This gate is quantified with Olney's ≥85% test-route rule.
3. After completion.

Inside the stages, use the expert micro-workflows: power stage (TI), BGA (Feranec), and a routing-priority ladder (TI SZZA009 / Olney).

Encode the checklist as a **three-tier critic stack**:
- (A) KiCad DRC plus generated custom rules.
- (S) Semantic-geometry critics driven by a role/constraint model that the LLM extracts from the schematic and datasheets.
- (J) An LLM judge plus simulation hooks.

Thresholds come from fab/assembler profiles and datasheets, each with recorded provenance. Version-gate the reuse features: multichannel needs KiCad ≥9; PCB design blocks need ≥10.

### Cited Findings (capabilities and prior art)
- **KiCad DRC** already covers many A-class items: clearance/creepage, unconnected items, starved thermals, edge/hole clearances, co-located drills, annular width, microvia rules, courtyards, slivers, mask bridges, schematic parity, length/skew/via count, diff-pair gap/uncoupled length, silkscreen clearance/clipping, text size and mirroring, isolated copper, zone intersections, and library mismatch — [KiCad DRC docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_inspecting.adoc) [P].
- **Custom-rule constraints**: `annular_width, assertion, bridged_mask, clearance, connection_width, courtyard_clearance, creepage, diff_pair_gap, diff_pair_uncoupled, disallow, edge_clearance, hole_clearance, hole_size, hole_to_hole, length, microvia_*, min_resolved_spokes, physical_*clearance, silk_clearance, skew, solder_mask_expansion, solder_paste_*, text_*, thermal_*, track_angle, track_segment_length, track_width, via_count, via_dangling, via_diameter, zone_connection`. **Conditions**: `A.NetClass`, `enclosedByArea()`, `intersectsArea()`, `intersectsCourtyard()`, `existsOnLayer()`, `fromTo()`, `getField()`, `hasComponentClass()`, `inDiffPair()`, `isCoupledDiffPair()` — [KiCad custom rules](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc) [P]. Component classes (with DRC query functions) arrived in KiCad 9.0 — [KiCad 9 release](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/) [P].
- **Reuse/placement primitives**:
  - select by sheet, Pack and Move, Move Individually, Auto-Place, Align/Distribute — [editing docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc) [P];
  - multichannel rule-area generation plus isomorphism-checked Repeat Layout (KiCad 9) — [docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_multichannel.adoc) [P];
  - PCB design blocks (KiCad 10) — [docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_design_blocks.adoc) [P]; [KiCad 10 release](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/) [P].
- **Expert process gates**:
  - Olney: fit check → placement → 85% test route → stackup/PDN/rules/router setup → fanout → critical routes locked → prioritized groups → per-net sanity check [P].
  - UW Rocketry's three PR review points [P].
  - VSE's staged reviews [P].
  - NASA: design review of the complete assembly before assembly [P].
- **Routing priority ladder**: TI SZZA009 (power/ground and susceptibility nets by hand → clocked data → autorouter only for <50 kHz) [P]; Olney (matched/diff/critical first, lock) [P]; Feranec (DDR: don't fully route groups sequentially) [P].
- **LLM review prior art**:
  - **aklofas/kicad-happy** (MIT, active Oct 2026) parses schematic, PCB and Gerbers into structured data. Its PCB analyzer documents connectivity (union-find), decoupling proximity, ground domains, trace proximity, current capacity, thermal-pad vias, via types/annular rings/via-in-pad, layer transitions, courtyard overlap, silkscreen, DFM tiering and tombstoning risk. It lists known limitations, including "Zone fill staleness" and "No impedance calculation" — [repo](https://github.com/aklofas/kicad-happy), [methodology_pcb.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_pcb.md) [P].
  - **Adom kicad-board-audit**: "run the real checkers first"; read silenced rule severities; group DRC by root cause; extract a pad-level netlist; walk each IC (power pins, mandatory passives, resets, straps, regulator dividers vs exact variant VFB, buses, crystals); layout audit (net-class coverage, diff skew, via styles, keepout flags, zones); "Every suspicious finding gets a primary source"; severity-ranked report (Critical/High/Medium/Low), with each finding giving refs, pins, why and one concrete fix — [Adom](https://wiki.adom.inc/adom/kicad-board-audit/files/SKILL.md) [P].
  - **claude-eda** encodes placement priorities and thresholds as prose — [repo](https://github.com/l3wi/claude-eda) [P].

### Inferences

**1. Agent plan as a state machine** (stages from the Q1 table; checklist IDs at each exit gate)

| State | Actions (KiCad ops) | Exit critics (IDs) | Gate | Backtrack on failure |
|---|---|---|---|---|
| S0 Intake & constraint model | LLM builds net classes (HS/diff/RF/power with current/HV with voltage), part roles (decap-of, crystal-of, ESD-of, hot-loop members, FB network, terminations) stored as **component classes/fields**; extracts per-IC layout rules from datasheet "Layout Guidelines"; loads fab/assembler profile into rules | PRC-01/05/07/10/11/12, STK-09, FP-01/02/07/12 | **Gate 1** (human or LLM review of the constraint model) | Fix schematic or ask a human |
| S1 Mechanical | Outline, holes, keepouts, height zones; lock | MEC-01..21, DFM-10 | C pass | — |
| S2 Stackup & PDN strategy | Pick a fab template; compute widths (craftyjon sanity rule); per-layer net-class rules; plane assignment | STK-01..12 | C pass | Revisited from S7/S11 |
| S3 Fit check | Pack all courtyards into the outline (Olney) | PLC-22 | Fits | → S1 (area) or flag a requirement |
| S4 Fixed parts | Connectors, UI, debug; lock | MEC-04..06/12/17/20 | C pass | → S1 |
| S5 Floorplan | Rule area per hierarchical sheet; private-part clusters per IC; blocks ordered by signal flow; domain separation | PLC-02..05, ANA-02, flow metric | Score ≥ threshold | → S1/S4 |
| S6 Critical placement | Micro-workflows: power stage (PLC-27), BGA trial-fanout (Feranec), crystals (PLC-07/24), RF; apply design-block memory if KiCad ≥10 and topology matches | PWR-01..03/08, PLC-07/12/24/27, RF-04 | C pass | → S5 |
| S7 Decoupling/support | Cross-select caps → per-pin placement in nF→µF→bulk order; ESD at connectors; terminations | PDN-01..04/11/15, PLC-05/06/08, EMC-01/07 | Thresholds met | → S6 |
| S8 Remaining + regularization | Place the rest; snap to grid; orientation/pin-1 normalization; Repeat Layout for channels | MEC-08, PLC-13..17/23/26, ASM-09..11, Q6 metrics | 0 overlaps | — |
| S9 Placement review (**Gate 2**) | Routability: HPWL, congestion, test route (≥85% per Olney); LLM review of renders + metrics | PLC-10/11, STK-06 | Pass | → S5–S8, or S2 (add layers) |
| S10 Fanout | Escape patterns, decap vias (own vias) | DFM-05/24, PST-01, PDN-03/11 | All escaped | → S6 |
| S11 Critical routing | Priority ladder: power/GND and susceptible nets → matched/diff/clocks → clocked data; escape-and-reserve for buses; lock | HS-01..06/13..21, GND-02/03/10, RF-01..03, PWR-02..04 | C pass | → S6/S10 |
| S12 Planes/pours | Pours; void/split checks; island removal | GND-01/04..08/11..13, PDN-05..08/14, ZON-01..07, THM-01/05/06 | C pass | → S11 |
| S13 Bulk routing | Remaining nets by priority group (any router) | PRC-03, RTE-01..09, HS-22/24 | 100% routed | → S8 or S2 |
| S14 Tuning & stitching | Meanders; GND stitching at transitions; RF fences; lock | HS-02/03, RF-02/03, GND-08, MEC-03 | Pass | → S11 |
| S15 Verify | Refill zones; DRC with severity audit; parity; DFM margin report; per-net Manhattan-ratio pass | All A-class items; PRC-02..04/12/13, CAM-01 | 0 C errors | Local repair → S13 |
| S16 Outputs | Silk cleanup, fiducials, fab/assembly drawings, stackup/impedance table, Gerber X2 + Excellon + IPC-356, re-parse outputs | SLK-*, ASM-*, CAM-*, PNL-* | Pass | — |
| S17 Sign-off (**Gate 3**) | LLM per-IC datasheet review; requirements review; human approval | PRC-06..09/14..16, all J items | Human | → any |

- Checkpoint every state as a git commit (the PR-per-review practice) so backtracking is cheap and reviewable.
- Escalate retries the way experts do: local moves → re-floorplan → repackage, add layers or enlarge the board → drop or flag functionality (Olney's options) → ask a human.

**2. Critic design**
- **Tier A** (deterministic; runs continuously, as MacroFab advises for CM DRC): generate a `.kicad_dru` from the role model and fab profile, run `kicad-cli pcb drc`, and map violation types to checklist IDs. **Audit severity overrides first** (PRC-12, Adom). Group findings by root cause (PRC-13).
- **Tier S** (semantic geometry; runs at stage exits). Each critic is `critic(board, roles, profile) -> [Finding{id, severity, objects, measured, threshold, threshold_source, evidence_png, fix}]`. Priority list by consensus × severity × hold data:
  1. Stackup/impedance/fab-note completeness and net-class coverage (STK-09/12, CAM-04).
  2. Reference-plane continuity under high-speed traces, including void distance and plane edge (GND-02/10).
  3. Current capacity of tracks and vias (PDN-06/07/13).
  4. Decap distance, order and own vias (PDN-01/02/11/15).
  5. Hot-loop and SW-node area (PWR-01/02).
  6. Return vias at transitions (GND-03).
  7. ESD series placement and filters at exits (EMC-06/07).
  8. Crystal isolation (PLC-07/24).
  9. Via-stub, antipad and symmetry rules on high-speed pairs (HS-17/18).
  10. Tombstone copper balance (THM-03).
  11. Assembler spacing tables (ASM-09/10).
- **Tier J** (LLM judge + simulation): for intent items (MEC-04/06/15, PRC-06/14, GND-04 split justification, ANA-01, option footprints), give the LLM a structured packet: item text and rationale from this table, datasheet excerpts, role model, cropped renders and the Tier A/S numbers. Require pass/fail/uncertain with evidence, and route "uncertain" to a human. Hand HS-08/14, FLX-07 and PWR-01 EMI to simulators.
- **Scoring**: Critical items gate stage exits. Major items are weighted penalties (weights from consensus and hold data). Minor items and Q6 aesthetic metrics become soft placement objectives, always paired with a coupling penalty (Olney's caveat).
- **Thresholds with provenance**: datasheet first, then fab/assembler profile, then house defaults. Tool heuristics (claude-eda 3 mm decap, kicad-happy 10 mm decap search radius, tombstone ratio 0.3) are labeled as unsourced. Sources conflict (silk height, edge clearance), so profiles are mandatory.

**3. Reuse**
- KiCad ≥9: hierarchical sheets map to rule areas; detect channels by isomorphism and Repeat Layout.
- KiCad ≥10: an **EVM-layout design-block library** keyed by MPN and topology (TI's "least risk" path), plus agent-learned blocks saved after they pass their critics.

**4. Coverage implication.** The recomputed stats above show about 37% of items (110 of 299, A or A/S) are fully automatable now, and a further ~41% (123, S or S/J) once the role model exists. That leaves ~22% (66, J) for LLM/human judgment or simulation. The LLM's distinctive jobs are therefore:
- (a) build the role/constraint model from schematic + datasheets (and verify it, as Adom insists);
- (b) plan and backtrack through the state machine, using expert micro-workflows;
- (c) judge the J residue and write severity-ranked findings with concrete fixes.

### Gaps
- No published, *evaluated* LLM-agent layout workflow was found. kicad-happy and Adom are review tools with unpublished accuracy.
- S-critic thresholds (acceptable hot-loop area, decap distance by package and frequency) are not standardized. They need datasheet extraction or calibration on expert-reviewed boards.
- This research did not verify whether the KiCad 10 IPC API exposes everything the S critics and design-block placement need, as opposed to pcbnew Python and `kicad-cli`.
