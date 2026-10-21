# Expert layout workflow as a backtracking state machine

**TL;DR**
- Experts agree on a constraint-first order: mechanics, stackup and rules come first; power/ground strategy before placement; critical nets routed by hand and locked before bulk routing.
- Expert judgment is concentrated in placement (states S3–S9). The explicit, quantified gate between placement and routing is Olney's test autoroute: at least 85% completion.
- The workflow maps onto an 18-state backtracking state machine with three review gates: constraint model, rough placement before routing, and sign-off.
- When a stage fails, experts escalate in a fixed order: local moves → re-floorplan → repackage, add layers or enlarge the board → drop or flag functionality → ask a human.
- Typical effort is 50 h for a simple board and about 200 h for a CPU+memory board (Feranec). The "90% placement" saying is folklore, not data.

## Key facts

Tags: [P] primary source read; [S] snippet/secondary; [V] vendor claim; [I] our inference. Practitioner quotes add a qualifier: [P/C] community opinion.

### Consensus order

Barry Olney's 2012 column is the most complete expert statement [P] ([iConnect007](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design); [ICD PDF](https://www.icd.com.au/articles/Interactive_Place_&_Route_PCBDesign-Dec2012.pdf)). The consensus sequence is:

mechanics/stackup/rules → power/ground strategy → fixed parts → functional floorplan → critical parts → decoupling → remaining parts → placement sanity check → fanout (often together with placement) → critical nets by hand, locked → planes → bulk routing → tuning and stitching → DRC/DFM → outputs.

Other sources:
- **JLCPCB** puts the "power distribution and grounding strategy" *before* component layout, and says of critical signals: "Manual First, Always" [P] ([JLCPCB process guide](https://jlcpcb.com/blog/pcb-layout-process-guide-2026-mastering-pcb-design)).
- **KiCad's Getting Started** gives a simple outline: outline → place → route → DRC → outputs [P].

### State table

This merges the expert-workflow note's Q1 workflow table with its agent state machine. Checklist IDs refer to [review-checklist.md](../verification/review-checklist.md).

| State | Expert action and decision | Exit gate (checklist IDs) | Loop-back |
|---|---|---|---|
| S0 Intake & constraint model | Review the schematic. Define net classes (high-speed, diff, RF, power with current, HV with voltage). Store part roles (decap-of, crystal-of, ESD-of, hot-loop members, FB network, terminations) as component classes or fields. Extract per-IC rules from the datasheet "Layout Guidelines". Load the fab/assembler profile into rules | **Gate 1**: PRC-01/05/07/10/11/12, STK-09, FP-01/02/07/12 | Fix the schematic or ask a human |
| S1 Mechanics | Set outline, holes, keepouts, height zones and connector positions from MCAD; use round dimensions and a coarse grid. "If you don't have any need to limit the size of the board, don't limit it too much" (eelik) | MEC-01..21, DFM-10 | From S3/S8 if area is short |
| S2 Stackup, rules, PDN strategy | Choose the minimum layer count and a fab standard stackup; compute per-layer impedance widths; assign planes; decide ground strategy ([stackup doc](board-size-layers-stackup.md)) | STK-01..12 | From S9/S13 if too dense |
| S3 Fit check | Pack all courtyards into the outline. This is the only use of autoplace Olney accepts | PLC-22 | → S1 (bigger board) or repackage |
| S4 Fixed parts | Place and lock connectors, UI, mounting holes, heatsinks and debug headers | MEC-04..06/12/17/20 | → S1 |
| S5 Floorplan | Gather each IC's private parts, then form functional blocks. Separate power/analog/digital/RF and order blocks by signal flow, with the fewest crossings between groups. Place by cross-probing, in order of importance | PLC-02..05, ANA-02, flow metric | → S1/S4 |
| S6 Critical placement | Run the [micro-workflows](sub-workflows-power-bga-ddr.md): BGA trial fanout; power stage (input cap placed **and routed** first); crystal; RF; terminations. Apply design-block memory if KiCad ≥10 | PWR-01..03/08, PLC-07/12/24/27, RF-04 | ↔ S10 |
| S7 Decoupling/support | Place caps per pin, nF → µF → bulk; each gets its own vias. Put ESD at connectors and terminations at the correct end | PDN-01..04/11/15, PLC-05/06/08, EMC-01/07 | → S6 |
| S8 Remaining + regularize | Place everything before routing. Snap to grid; normalize orientation and pin 1; use Repeat Layout for channels | MEC-08, PLC-13..17/23/26, ASM-09..11 | — |
| S9 Placement review | Ratsnest, HPWL, congestion; **test autoroute ≥85%**; formal placement review | **Gate 2**: PLC-10/11, STK-06 | → S5–S8, or S2 (add layers) |
| S10 Fanout | Escape patterns; decap vias (own vias) | DFM-24, PST-01, PDN-03/11 | → S6 |
| S11 Critical routing | Follow the priority ladder; escape-and-reserve for buses; lock | HS-01..06/13..21, GND-02/03/10, RF-01..03, PWR-02..04 | → S6/S10 |
| S12 Planes/pours | Solid reference planes; split only with justification; remove islands | GND-*, PDN-05..08/14, ZON-*, THM-01/05/06 | → S11 |
| S13 Bulk routing | Route the remaining nets in priority groups. Only nets switching below 50 kHz are "safe" for an autorouter (TI 1999) | PRC-03, RTE-01..09, HS-22/24 | → S8 or S2 |
| S14 Tuning & stitching | Meander at the mismatched end; GND stitching at layer transitions; RF fences; lock | HS-02/03, RF-02/03, GND-08 | → S11 |
| S15 Verify | Refill zones; run DRC with a silenced-rule audit; check parity; DFM margin report; per-net Manhattan-ratio pass | All A-class items, PRC-02..04/12/13, CAM-01 | Local repair → S13 |
| S16 Outputs | Clean up silkscreen; fiducials; fab/assembly drawings; stackup/impedance table; Gerber X2 + Excellon + IPC-356; re-parse the outputs | SLK-*, ASM-*, CAM-*, PNL-* | — |
| S17 Sign-off | Per-IC datasheet review; requirements review; human approval tied to a commit | **Gate 3**: PRC-06..09/14..16, J items | → any |

**Olney's gate** [P]: "If you do not get at least 85% completion on this first test route, then you may need to tweak the placement, look at more appropriate packaging, adjust the design rules, and possibly drop some functionality."

**Further Olney practices** [P]:
- Place "one component at a time" by cross-probing from the schematic. A select list cannot tell "a trivial static pull-up resistor" from "a critical terminator".
- Highlight each net in turn to find nets "longer than the Manhattan length or spiral around the board three times".

### Review gates (iteration checkpoints)

| Source | Gates |
|---|---|
| UW Rocketry [P] ([Confluence](https://uwaterloo.atlassian.net/wiki/spaces/ROCKETRY/pages/43024155641/Design+Reviews)) | Three reviews on the same PR: after schematics; "When you've roughly laid out your PCB but haven't done any routing (… it's much easier to make significant layout changes before doing routing)"; and at completion. The reviewee posts the checks performed, tied to a commit |
| VSE [P] ([VSE](https://www.vse.com/blog/a-pcb-layout-checklist-for-error-free-manufacturing/)) | "a pre-layout review, a component placement review, and a critical routing review", each with its own checklist |
| Flux [P] | Separate schematic, layout and DFM reviews |
| bestpcbs [P] | Run DFM "before quotation, before prototype release, before production release, and whenever the board changes material, layer count, package density, or assembly method" |
| NASA GSFC-STD-8001A [P] | "A design review of the complete circuit board assembly should precede the PCB assembly process" |
| Phil's Lab #85 [P/E, chapter titles only] | PCB review order: stack-up → switching regulator → rules, via sizing, power → outline and mounting holes → FPGA power and decoupling → transfer vias → diff pairs → clearance, pours, planes → silkscreen/USB-C ([FEDEVEL mirror](https://home.fedevel.com/blog/fpga-pcb-design-review-phils-lab-85)) |

### Time budgets

| Source | Claim | Tag |
|---|---|---|
| Feranec | "simple boards are up to 50 hours, more complex boards (with a CPU and memory) starts around 200 hours"; length matching "took quite a lot" ([FEDEVEL](https://designhelp.fedevel.com/forum/fedevel-academy/course-questions-no-electronic/2472-how-to-price-projects)) | [P] |
| Folklore | "90% placement and 10% routing" | [S] |
| PCD&F 2019 | "90% of the routing on a PCB takes only 10% of the time, while 10% of the remaining routing can take 90% of the time" | [P] |
| Siemens | "majority of design time is spent on placement and routing" (no study cited); automation can "accelerate design cycle times up to 50% or more". The "80%" figure was not found on the page | [V] |
| DeepPCB | "Constraint definition alone can take days on a complex board" | [V] |
| cushychicken | Schematic capture is under 10% of the time | [P/C] |
| BadeBhaiya | Symbols ~1%, schematic+layout ~20%, "The rest 80% … is decision making around constraints" | [P/C] |
| MonMotha | "almost as much time floorplanning and placing … as it is actually routing" | [P/C] |
| Quilter Linux board | ~27 h of parallel seeded runs plus human cleanup, vs Tesla500's ~38 h manual layout (rasz counts 38.5 h of human assistance) | [P/C] |

### Practitioner placement procedures (S3–S8 in practice)

Tags as above; [P/A] marks a single practitioner's anecdote.

- **Iterate on the ratsnest.**
  - kenyapcomau: "it's an iterative process … watch what happens to the rats nest … Then I hit some constraint and I may have to try a different layout … Sometimes I even modify the circuit."
  - Rerouter: group each chip's private parts first, "move them around until the least number of traces would have to cross" ([KiCad forum 23682](https://forum.kicad.info/t/strategy-to-use-for-placing-components/23682)) [P/C].
- **Clustering heuristics.**
  - thinkfat: "grouped parts together based on the 'length' and count of crossings of ratsnest lines".
  - Rerouter: cluster by fewest unique nets.
  - davidsrsb: a total-ratsnest-length metric with net weighting [P/C].
- **Large designs** (KiCad 8 workflow):
  - Cross-probe, select a schematic block, press "P" (Pack and Move), then place and route it, group it and move groups.
  - PigHillJimster uses reference-designator ranges (x3nn power, x5nn MCU) and agrees fixed-part positions with the mechanical engineer from a STEP file [P/C].
  - Fixed parts first, then functional "nuggets" and paper sketching ([KiCad forum 51620](https://forum.kicad.info/t/pcb-layout-strategy/51620)) [P/C].
- **Autoplace with locks.** nigelwright7557: rough placement → "Swap autoplace" for shortest nets, with "Anything I dont want moving is set as 'unmovable'" → autoroute → fix star grounding → pours [P/A]. CadMust users immediately ask to lock connectors [P/C].
- **Packing seeds.** seveibar (tscircuit):
  - "CSS grid-style constraints are a much better fit"; "settled on sequential optimal packing for 'seeding' a placement so that AI can get initial positions before working in a feedback loop".
  - Pure area-minimizing packing yields "a board that is nearly impossible to route", and force-directed placement is "wildly unpredictable" ([blog](https://blog.autorouting.com/p/sequential-optimal-packing-for-pcb)) [V].
  - lambdaone: "place them wrongly, and you will have to get used to seeing the word UNFEASIBLE"; use hierarchical decomposition [P/A].
  - monocasa frames placement as bin-packing [P/C].
- **Refine, don't restart.** KRT's placement doc: "The killer isn't the algorithm — it's constraint capture". Prefer perturbative refinement from a seed over from-scratch placement, with router-in-the-loop repair (`place_route_loop.py`). Quilter's 2026 changes (floorplan page, pin-distance constraint, region clustering with anchoring) point the same way (VK) [P].
- **Expect to edit the schematic.** In practice placement and routing are not separate: "move / rotate parts while doing the routing... changing the case / pinout of some parts... swapping equivalent pins" (Kleinstein). Sprig: "Layout done first, schematic drawn second, and firmware developed third" for software-controlled pin designs [P/C].

## Recommendations for our system

- Make the agent's first placement output a floorplan of regions, pre-placed connectors, anchors and pin-distance constraints, confirmed by the user before any numeric optimizer runs. Then refine from that seed [I].
- Implement S0–S17 as an explicit backtracking state machine with critic-gated exits. Checkpoint every state as a git commit, mirroring UW Rocketry's PR-per-review practice [I].
- Make the three gates real stops, with human or LLM review of the constraint model (Gate 1), the placement (Gate 2) and sign-off (Gate 3) [I].
- Spend most search effort on S3–S9. Use a fast routability probe as the inner-loop objective, and make the ≥85% threshold a profile parameter [I].
- Encode Olney's escalation ladder as the retry policy, ending with an explicit human question [I].
- Treat the ladder of micro-workflows as sub-plans: see [sub-workflows-power-bga-ddr.md](sub-workflows-power-bga-ddr.md).

## Conflicts and open questions

- No primary source splits expert hours by phase in extractable form. Feranec's timesheet graphs are images that were not extracted.
- No published, *evaluated* LLM-agent layout workflow exists. kicad-happy and the Adom audit skill are review tools with unpublished accuracy.
- Whether the KiCad 10 IPC API can execute every state's actions is unverified; see [../kicad/ipc-api.md](../kicad/ipc-api.md).

## Sources

- research notes: [expert_workflow_and_checklists.md § Q1 workflow; § Implications (state machine)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- research notes: [practitioner_discussions.md § Q2–Q3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- primary: [Olney 2012](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design), [UW Rocketry reviews](https://uwaterloo.atlassian.net/wiki/spaces/ROCKETRY/pages/43024155641/Design+Reviews), [VSE checklist](https://www.vse.com/blog/a-pcb-layout-checklist-for-error-free-manufacturing/), [PCD&F 2019](https://www.qgdigitalpublishing.com/article/PCB+Guided+Insights/3388181/589425/article.html)

See also: [sub-workflows-power-bga-ddr.md](sub-workflows-power-bga-ddr.md), [board-size-layers-stackup.md](board-size-layers-stackup.md), [layout-reuse.md](layout-reuse.md), [../verification/critic-stack.md](../verification/critic-stack.md)
