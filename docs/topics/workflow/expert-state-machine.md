# Expert layout workflow as a backtracking state machine

Scope: consensus expert layout order, mapped to an 18-state backtracking state machine with three review gates; time budgets; practitioner placement procedures. Not here: micro-workflows (power, BGA, DDR) -> [sub-workflows-power-bga-ddr.md](sub-workflows-power-bga-ddr.md); board size/stackup -> [board-size-layers-stackup.md](board-size-layers-stackup.md).
Keys: S0–S17, Gate 1, Gate 2, Gate 3, Olney 85% test autoroute, escalation ladder, constraint-first order, floorplan, cross-probing, review gates, UW Rocketry, Phil's Lab #85, time budget, Feranec 50 h / 200 h, 90% placement folklore, perturbative refinement

Tags: [P] primary; [S] snippet/secondary; [V] vendor; [I] inference; [P/E] expert; [P/C] community opinion; [P/A] anecdote.

## Consensus order

Most complete statement: Barry Olney 2012 [P] ([iConnect007](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design); [ICD PDF](https://www.icd.com.au/articles/Interactive_Place_&_Route_PCBDesign-Dec2012.pdf)).

```
mechanics/stackup/rules → power/ground strategy → fixed parts → functional floorplan
→ critical parts → decoupling → remaining parts → placement sanity check
→ fanout (often with placement) → critical nets by hand, locked → planes
→ bulk routing → tuning and stitching → DRC/DFM → outputs
```

- JLCPCB: "power distribution and grounding strategy" before component layout; critical signals "Manual First, Always" ([process guide](https://jlcpcb.com/blog/pcb-layout-process-guide-2026-mastering-pcb-design)) [P].
- KiCad Getting Started: outline → place → route → DRC → outputs [P].
- Expert judgment concentrates in placement (S3–S9) [I].

## State table

Merges the expert-workflow note's Q1 workflow table with its agent state machine. Checklist IDs -> [review-checklist.md](../verification/review-checklist.md).

| State | Expert action and decision | Exit gate (checklist IDs) | Loop-back |
|---|---|---|---|
| S0 Intake & constraint model | Review schematic. Net classes (high-speed, diff, RF, power with current, HV with voltage). Part roles (decap-of, crystal-of, ESD-of, hot-loop members, FB network, terminations) as component classes or fields. Per-IC rules from datasheet "Layout Guidelines". Fab/assembler profile into rules | **Gate 1**: PRC-01/05/07/10/11/12, STK-09, FP-01/02/07/12 | Fix schematic or ask a human |
| S1 Mechanics | Outline, holes, keepouts, height zones, connector positions from MCAD; round dimensions, coarse grid. "If you don't have any need to limit the size of the board, don't limit it too much" (eelik) | MEC-01..21, DFM-10 | From S3/S8 if area short |
| S2 Stackup, rules, PDN strategy | Minimum layer count, fab standard stackup; per-layer impedance widths; planes; ground strategy ([stackup doc](board-size-layers-stackup.md)) | STK-01..12 | From S9/S13 if too dense |
| S3 Fit check | Pack all courtyards into the outline; the only autoplace use Olney accepts | PLC-22 | → S1 (bigger board) or repackage |
| S4 Fixed parts | Place and lock connectors, UI, mounting holes, heatsinks, debug headers | MEC-04..06/12/17/20 | → S1 |
| S5 Floorplan | Gather each IC's private parts, then functional blocks. Separate power/analog/digital/RF; order blocks by signal flow, fewest inter-group crossings. Place by cross-probing, in order of importance | PLC-02..05, ANA-02, flow metric | → S1/S4 |
| S6 Critical placement | [Micro-workflows](sub-workflows-power-bga-ddr.md): BGA trial fanout; power stage (input cap placed **and routed** first); crystal; RF; terminations. Design-block memory if KiCad ≥10 | PWR-01..03/08, PLC-07/12/24/27, RF-04 | ↔ S10 |
| S7 Decoupling/support | Caps per pin, lowest mounting inductance closest (value order nF → µF → bulk only behind the contested-rule selector, [../rules/decoupling-pdn.md](../rules/decoupling-pdn.md)); each with own vias. ESD at connectors; terminations at correct end | PDN-01..04/11/15, PLC-05/06/08, EMC-01/07 | → S6 |
| S8 Remaining + regularize | Place everything before routing. Snap to grid; normalize orientation and pin 1; Repeat Layout for channels | MEC-08, PLC-13..17/23/26, ASM-09..11 | — |
| S9 Placement review | Ratsnest, HPWL, congestion; **test autoroute ≥85%**; formal placement review | **Gate 2**: PLC-10/11, STK-06 | → S5–S8, or S2 (add layers) |
| S10 Fanout | Escape patterns; decap vias (own vias) | DFM-24, PST-01, PDN-03/11 | → S6 |
| S11 Critical routing | Priority ladder; escape-and-reserve for buses; lock | HS-01..06/13..21, GND-02/03/10, RF-01..03, PWR-02..04 | → S6/S10 |
| S12 Planes/pours | Solid reference planes; split only with justification; remove islands | GND-*, PDN-05..08/14, ZON-*, THM-01/05/06 | → S11 |
| S13 Bulk routing | Remaining nets in priority groups; only nets switching <50 kHz "safe" for an autorouter (TI 1999) | PRC-03, RTE-01..09, HS-22/24 | → S8 or S2 |
| S14 Tuning & stitching | Meander at the mismatched end; GND stitching at layer transitions; RF fences; lock | HS-02/03, RF-02/03, GND-08 | → S11 |
| S15 Verify | Refill zones; DRC with silenced-rule audit; parity; DFM margin report; per-net Manhattan-ratio pass | All A-class items, PRC-02..04/12/13, CAM-01 | Local repair → S13 |
| S16 Outputs | Silkscreen cleanup; fiducials; fab/assembly drawings; stackup/impedance table; Gerber X2 + Excellon + IPC-356; re-parse outputs | SLK-*, ASM-*, CAM-*, PNL-* | — |
| S17 Sign-off | Per-IC datasheet review; requirements review; human approval tied to a commit | **Gate 3**: PRC-06..09/14..16, J items | → any |

Olney's gate [P]: "If you do not get at least 85% completion on this first test route, then you may need to tweak the placement, look at more appropriate packaging, adjust the design rules, and possibly drop some functionality." One source (Olney 2012; Autodesk repeats it); completion depends on router, pass budget, rules and pre-routed nets → treat ≥85% as an uncalibrated profile parameter [I].

Escalation ladder on stage failure: local moves → re-floorplan → repackage / add layers / enlarge board → drop or flag functionality → ask a human. Use it as the retry policy [I].

Olney practices [P]: place "one component at a time" by cross-probing; a select list cannot tell "a trivial static pull-up resistor" from "a critical terminator". Highlight each net to find nets "longer than the Manhattan length or spiral around the board three times".

Implementation [I]:
- Explicit backtracking state machine with critic-gated exits; checkpoint each state as a git commit (mirrors UW Rocketry's PR-per-review).
- Gate 1 (LLM-authored constraint model) and Gate 3 (sign-off) need a human: S17 requires human approval tied to a commit; the IR requires a human to confirm LLM-authored constraints ([../architecture/constraint-ir.md](../architecture/constraint-ir.md)). An LLM may pre-review but cannot pass them. Gate 2 may use human or LLM review.
- Spend most search effort on S3–S9 with a fast routability probe as inner-loop objective.
- First placement output: a floorplan of regions, pre-placed connectors, anchors and pin-distance constraints, confirmed by the user before any numeric optimizer; then refine from that seed.

## Review gates (iteration checkpoints)

| Source | Gates |
|---|---|
| UW Rocketry [P] ([Confluence](https://uwaterloo.atlassian.net/wiki/spaces/ROCKETRY/pages/43024155641/Design+Reviews)) | Three reviews on the same PR: after schematics; "When you've roughly laid out your PCB but haven't done any routing (… it's much easier to make significant layout changes before doing routing)"; at completion. Reviewee posts checks performed, tied to a commit |
| VSE [P] ([VSE](https://www.vse.com/blog/a-pcb-layout-checklist-for-error-free-manufacturing/)) | "a pre-layout review, a component placement review, and a critical routing review", each with its own checklist |
| Flux [P] | Separate schematic, layout and DFM reviews |
| bestpcbs [P] | DFM "before quotation, before prototype release, before production release, and whenever the board changes material, layer count, package density, or assembly method" |
| NASA GSFC-STD-8001A [P] | "A design review of the complete circuit board assembly should precede the PCB assembly process" |
| Phil's Lab #85 [P/E, chapter titles only] | Review order: stack-up → switching regulator → rules, via sizing, power → outline and mounting holes → FPGA power and decoupling → transfer vias → diff pairs → clearance, pours, planes → silkscreen/USB-C ([FEDEVEL mirror](https://home.fedevel.com/blog/fpga-pcb-design-review-phils-lab-85)) |

## Time budgets

| Source | Claim | Tag |
|---|---|---|
| Feranec | "simple boards are up to 50 hours, more complex boards (with a CPU and memory) starts around 200 hours"; length matching "took quite a lot" ([FEDEVEL](https://designhelp.fedevel.com/forum/fedevel-academy/course-questions-no-electronic/2472-how-to-price-projects)) | [P] |
| Folklore | "90% placement and 10% routing" (not data) | [S] |
| PCD&F 2019 | "90% of the routing on a PCB takes only 10% of the time, while 10% of the remaining routing can take 90% of the time" | [P] |
| Siemens | "majority of design time is spent on placement and routing" (no study cited); automation can "accelerate design cycle times up to 50% or more"; the "80%" figure not found on the page | [V] |
| DeepPCB | "Constraint definition alone can take days on a complex board" | [V] |
| cushychicken | Schematic capture <10% of the time | [P/C] |
| BadeBhaiya | Symbols ~1%, schematic+layout ~20%, "The rest 80% … is decision making around constraints" | [P/C] |
| MonMotha | "almost as much time floorplanning and placing … as it is actually routing" | [P/C] |
| Quilter Linux board | rasz: 38.5 h human assistance with Quilter vs Tesla500's ~38 h manual layout; Quilter's ~27 h of parallel seeded runs are compute on top, then human cleanup | [P/C] |

## Practitioner placement procedures (S3–S8 in practice)

| Procedure | Evidence | Tag |
|---|---|---|
| Iterate on the ratsnest | kenyapcomau: "it's an iterative process … watch what happens to the rats nest … Then I hit some constraint and I may have to try a different layout … Sometimes I even modify the circuit." Rerouter: group each chip's private parts first, "move them around until the least number of traces would have to cross" ([KiCad forum 23682](https://forum.kicad.info/t/strategy-to-use-for-placing-components/23682)) | [P/C] |
| Clustering heuristics | thinkfat: group by "'length' and count of crossings of ratsnest lines"; Rerouter: fewest unique nets; davidsrsb: total-ratsnest-length metric with net weighting | [P/C] |
| Large designs (KiCad 8) | Cross-probe, select a schematic block, "P" (Pack and Move), place and route it, group it, move groups. PigHillJimster: refdes ranges (x3nn power, x5nn MCU); fixed-part positions agreed with the mechanical engineer from a STEP file. Fixed parts first, then functional "nuggets" and paper sketching ([KiCad forum 51620](https://forum.kicad.info/t/pcb-layout-strategy/51620)) | [P/C] |
| Autoplace with locks | nigelwright7557: rough placement → "Swap autoplace" for shortest nets, "Anything I dont want moving is set as 'unmovable'" → autoroute → fix star grounding (audio) → pours [P/A]. CadMust users immediately ask to lock connectors [P/C] | [P/A] |
| Packing seeds | seveibar (tscircuit): "CSS grid-style constraints are a much better fit"; "settled on sequential optimal packing for 'seeding' a placement so that AI can get initial positions before working in a feedback loop"; pure area-minimizing packing → "a board that is nearly impossible to route"; force-directed "wildly unpredictable" ([blog](https://blog.autorouting.com/p/sequential-optimal-packing-for-pcb)) [V]. lambdaone: "place them wrongly, and you will have to get used to seeing the word UNFEASIBLE"; hierarchical decomposition [P/A]. monocasa: bin-packing [P/C] | [V] |
| Refine, don't restart | KRT placement doc: "The killer isn't the algorithm — it's constraint capture"; perturbative refinement from a seed over from-scratch, router-in-the-loop repair (`place_route_loop.py`). Quilter 2026 changes (floorplan page, pin-distance constraint, region clustering with anchoring) point the same way (VK) | [P] |
| Expect to edit the schematic | "move / rotate parts while doing the routing... changing the case / pinout of some parts... swapping equivalent pins" (Kleinstein). Sprig: "Layout done first, schematic drawn second, and firmware developed third" for software-controlled pin designs | [P/C] |

## Open questions

- Olney's ≥85% has one source; janvi reports from-scratch autorouting "rarely over 80%" ([autorouter-distrust.md](autorouter-distrust.md#where-routers-help-probe-vs-producer)), so the threshold depends on probe router and budget.
- No primary source splits expert hours by phase in extractable form; Feranec's timesheet graphs are unextracted images.
- No published, *evaluated* LLM-agent layout workflow exists; kicad-happy and the Adom audit skill are review tools with unpublished accuracy.
- Whether the KiCad 10 IPC API can execute every state's actions is unverified -> [../kicad/ipc-api-10-vs-11.md](../kicad/ipc-api-10-vs-11.md).

## Sources

- [expert_workflow_and_checklists.md § Q1 workflow; § Implications (state machine)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- [practitioner_discussions.md § Q2–Q3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- primary: [Olney 2012](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design), [UW Rocketry reviews](https://uwaterloo.atlassian.net/wiki/spaces/ROCKETRY/pages/43024155641/Design+Reviews), [VSE checklist](https://www.vse.com/blog/a-pcb-layout-checklist-for-error-free-manufacturing/), [PCD&F 2019](https://www.qgdigitalpublishing.com/article/PCB+Guided+Insights/3388181/589425/article.html)
- See also: [layout-reuse.md](layout-reuse.md), [../verification/critic-stack.md](../verification/critic-stack.md)
