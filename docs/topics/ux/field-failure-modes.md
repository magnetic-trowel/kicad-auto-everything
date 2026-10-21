# Field failure modes of LLM-driven PCB work (taxonomy)

**TL;DR**
- **The costliest failures are invisible to DRC/ERC:** wrong package variants, same-name footprint aliasing, label-collision shorts that ERC only warns about, ratings, and muted rule categories [P, anecdote].
- **"The API said OK" is not evidence.** Calls returned success while dropping GND connections, attributes or 3D models; a write "succeeded" with zero bytes changed; a batch ran twice [P].
- **Many failures are tool bugs:** rotation math, a saved file vs the live board, approximate courtyard checks. The agent chases phantom errors or misses real ones [S].
- **Agents loop:** they do not know when to stop, and autofix loops miss failure categories. Loop budgets and escalation are required [P, anecdote].
- **DRC-clean can coexist with an unusable layout:** about 10,000 zigzag segments, "horrendous tracks", a blocked USB port [P, anecdote].

## Key facts

| Category | Concrete examples (source) | Workaround seen |
|---|---|---|
| **Footprint and package errors** | W25Q128JVS SOIC-8-wide on SOP-8 pads; an invented package ([A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/)). "Claude will get the component footprints wrong from time to time" ([MakeUseOf](https://www.makeuseof.com/pcb-design-easier-thanks-to-claude/)). "Invented footprints are the most expensive failure… nothing catches them until assembly" ([Cherry Blossom](https://www.trycherryblossom.com/blog/gpt-6-astra-pcb-design)) | Real part data for every footprint; footprint vs MPN/datasheet check |
| **Library aliasing** | Shared `C0603` names merged in EasyEDA's cache: 50 pad-association mismatches over 120 pads, with all nets reading correct ([JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-easyeda-pro)) | Unique footprint names; library-identity uniqueness check |
| **Missing connections despite API success** | 6 missing GNDs found by 138/138 read-back ([JLCPCB](https://jlcpcb.com/blog/claude-code-pcb-design)); unwired parts (atomic14 [S]) | Read-back netlist and pin-by-pin diff |
| **Label collision shorts** | ISENSE shorted to ISET; ERC only warned ([JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code)) | Pin-for-pin netlist comparison against the spec |
| **Rotation and coordinate math** [S] | Textbook rotation matrix where KiCad uses the transpose (mcp-server-kicad PR #59); `move_footprint(rotation)` left pad and text angles stale (#110 → one orientation helper, #125); schematic-sync angles (kicad-mcp-pro #1319); keepouts written in local coordinates (#128); LLM inverse rotations for labels (Copperhead #398). nexatech: "pad angles in the board file are absolute" (201/1,763 wrong, "and the gate still passed"); "Flip… is a mirror in Y plus 180°"; "where pad 1 goes under rotation is measured, not derived" | One shared orientation helper through KiCad's own code |
| **Data loss on edit** [S] | kicad-python's orientation setter rebuilt footprints and dropped 3D models, text boxes and dimensions (KiCAD-MCP-Server #422; kicad-mcp-pro #1321) | Preserve-all transforms; observed-diff read-back |
| **State divergence** | **A scorer read the saved file while KiCad held live moves, hiding a ~4.0 mm² courtyard overlap** (Konnect #595/#628/#648 [S]). `SaveBoard` silently changed a via's net ("three hours went into 'the router can't see its via'"). pcb-rnd `SaveTo` produced 5 copper layers ([tinycomputers](https://tinycomputers.io/posts/what-routing-314-nets-taught-me-about-ai-assisted-pcb-design.html)). An ERC count quoted from a log 58 s older than the last save | Judge the live board and report the source; input fingerprints on gate verdicts |
| **Writes and checks that lie** | "A write that didn't happen reports success" ("widened 36 segments", none changed: `0.15` vs `0.1500`). **"A check that didn't run reports zero"** (6 silent-clean cases). A `--severity-error` filter hid 20 hole_to_hole items, 19 below the fab minimum ([nexatech](https://raw.githubusercontent.com/nexatech-ltd/kicad-agent-toolkit/main/docs/lessons-learned.md)) | Checked / defect / not-checked states; diff after write |
| **Checks that disagree with KiCad** [S] | Single-AABB courtyard false overlaps (KiCAD-MCP-Server #406); pad-bbox fallback warnings (kicad-tools #4227); `check_clearance` measured anchor distance (Konnect #528); pcb-rnd's 121 false-positive clearance flags at same-net junctions (about 6 h) | Never re-implement approximations; use kicad-cli; compare several DRC tools; fab DFM as truth |
| **Fab rules not configured** [S] | Freerouting used the 0.2 mm default instead of hole edge clearance (#419); traces through mounting holes via `::1` suffixes (freerouting #951); necking to 0.15 mm gave 22 DRC; multithreaded optimizer violations → `-mt 1` (kicad-cli #32); Claude's A* router at 0.35 vs 0.5 mm edge clearance | Fab-specific rules as a precondition; Freerouting `-mt 1` |
| **Muted checks** | "Zero violations" with 5 DRC + 4 ERC categories ignored ([JLCPCB Astra](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad)); ERC 0/0 while MCU VCAP pins floated ([Adom](https://wiki.adom.inc/api/pages/adom/kicad-board-audit/files/README.md)) | Every clean report lists disabled categories; read silenced-rule config |
| **ERC/DRC-blind defects** | Floating VCAP pins, supply pins tied to GND, wrong-variant VFB dividers, missing pull-ups, crystal load caps (Adom). The GUI's F8 found transistor pin mismatches that ERC, DRC and parity all missed (nexatech). "Topology isn't values": mode resistors must cite the datasheet row | Semantic checklists; human F8 at milestones; expected-value checks |
| **Ugly or weak layout that passes DRC** | haohao: about 10,000 zigzag segments and 4 pours → 600 segments, 30 vias, 1 plane, a third less area. "Front: beautiful placement… Back: horrendous tracks" (A6M-Zero). EEVblog: a bird's nest "would pass unnoticed by the AI, the simulator and the router alike" [S] | Readability metrics; style presets; human review |
| **Mechanical issues found late** | Blocked USB port, wrong fuse pitch, duplicate terminal block found by a late 1:1 paper check ([haohao](https://github.com/haohao-0725/PCB_Layout_with_AGENT_in_KiCAD)); antenna keepout and module placement (Tindie); "must be on edge" vs "nice to have" context missing (Autocuro) | 1:1 or 3D fit gate before routing; hard vs soft mechanical constraints |
| **Endless loops and not stopping** | Claude "happily kept trying to fix it… not as good at helping you recognize that the correct solution is to stop trying" (tinycomputers). An autofix loop ignored the "unconnected" DRC category, so unrouted boards were never re-routed (blwfish #158 [S]). A $10 cap was "all that stood between" a firmware agent and a $500 bill (StationX) | Retry caps (2–3); spend caps; recognize every category; escalate |
| **Debugging interfaces the LLM can't run** | "LLMs are not good at debugging interfaces they can't run" (tinycomputers, cross-tool DRC issue) | Run tools; give the LLM structured outputs |
| **GUI and API connection gotchas** | A second KiCad window steals the API; **a modal dialog blocks all API calls**; the board must be open; the API is disabled by default (JLCPCB); `open_board` 30 s timeout on large boards (PowerLabKiCadAssistant #61 [S]); bridge killed by low memory; the DRC API returns counts only; `importChanges()` needs a human click | Headless kicad-cli fallback; precondition checks |
| **Scale limits** | Validated only to 63 footprints; the 437-footprint HackRF failed; Freerouting crash-looped for 1 h; `add_zone(fill)` crashes after 3–4 calls ([Gato513](https://github.com/Gato513/kicad-mcp)) | Publish limits; per-region work |
| **Unsafe automation** [S] | A force-directed refiner "scrambles flagged components without converging" (Konnect #597); net-based decap guessing removed in favour of exact refs (#638); connector filter caps mis-scored as decaps (#416); a placement batch ran twice (JLCPCB) | Exact references; "applicable" only if the score improves; idempotency |
| **Agent input robustness** [S] | Local models used wrong dict keys and placeholder paths (blwfish #143); viewer data dropped pad names, so REFDES:PIN failed (HTMLPCBViewer #90) | Input validation; include pad names |
| **Non-determinism** | Same request, different coordinates (KiCad Agentic MCP); computer use "may take a different path and land on a different board" | Deterministic solver given constraints; record seeds |
| **Hallucinated defaults** | "The most dangerous hallucination… is inheriting the internet's defaults" (NE555 at 3 V); LLMs "*loved* to give naive advice about decoupling" (JITX); part selection "uniformly bad" | Datasheet-grounded checks; label inferences |
| **Placement-specific traps** (nexatech) | "QFN pins are locked by local support parts, not board size" (+10 mm gave 136 vs 118 breaks); `declash` moved by courtyard and ignored copper (1 fixed, 59 new); simplified search said "nowhere" while exact search found 6,254 positions; hiding vias made Freerouting 6× faster but produced 149 shorts | Exact-rule search; judge helpers by the acceptance verdict |

## Recommendations for our system

1. Every failure category above needs a **named check or guard**. See [agent-tooling-reliability-patterns.md](agent-tooling-reliability-patterns.md) [I].
2. A **semantic checker suite** beyond DRC/ERC:
   - footprint vs MPN/datasheet (pad count, pitch, body, variant);
   - library-identity uniqueness;
   - ratings vs net voltage and current;
   - an ERC-blind checklist;
   - layout-quality metrics (decap distance, loop area, ampacity, return path, skew, congestion, readability).
3. A **"clean" report always states what was disabled or not checked;** never a bare green.
4. **Escalate rather than loop:** stop after 2–3 failed fixes per issue, and present evidence and options.

## Conflicts and open questions

- GitHub items are snippet-level, since issue pages were blocked.
- Cherry Blossom published no failure taxonomy for its 40 boards.
- How common each failure is across projects is unknown.

## Sources
- research notes: [field_reports_and_ux.md § 1A, § 1A2, § 1C, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)

See also: [field-reports.md](field-reports.md), [agent-tooling-reliability-patterns.md](agent-tooling-reliability-patterns.md), [../kicad/mcp-server-lessons.md](../kicad/mcp-server-lessons.md), [../kicad/transform-math-pitfalls.md](../kicad/transform-math-pitfalls.md)
