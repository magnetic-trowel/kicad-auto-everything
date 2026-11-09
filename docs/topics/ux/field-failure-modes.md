# Field failure modes of LLM-driven PCB work (taxonomy)

Scope: taxonomy of failures seen in LLM-driven PCB projects, with examples and observed workarounds. Not here: the case studies themselves -> [field-reports.md](field-reports.md); guard designs -> [agent-tooling-reliability-patterns.md](agent-tooling-reliability-patterns.md); transform math -> [../kicad/transform-math-pitfalls.md](../kicad/transform-math-pitfalls.md); MCP bug classes -> [../kicad/mcp-server-lessons.md](../kicad/mcp-server-lessons.md).
Keys: failure taxonomy, footprint error, package variant, library aliasing, API success lies, read-back, label collision short, rotation math, state divergence, saved vs live board, silent-clean check, muted DRC categories, ERC-blind defects, DRC-clean but ugly, endless loops, retry cap, modal dialog blocks API, scale limits, non-determinism, hallucinated defaults

**Results**
- Costliest failures are invisible to DRC/ERC (package variants, aliasing, label shorts, ratings, muted categories) [P, anecdote].
- "The API said OK" is not evidence: read back every write [P].
- Many failures are tool bugs (rotation math, saved file vs live board, approximate courtyard checks): the agent chases phantom errors or misses real ones [S].
- Agents don't know when to stop; autofix loops miss failure categories → loop budgets and escalation required [P, anecdote].

## Failure categories

| Category | Concrete examples (source) | Workaround seen |
|---|---|---|
| Footprint and package errors | W25Q128JVS SOIC-8-wide on SOP-8 pads; an invented package ([A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/)). "Claude will get the component footprints wrong from time to time" ([MakeUseOf](https://www.makeuseof.com/pcb-design-easier-thanks-to-claude/)). "Invented footprints are the most expensive failure… nothing catches them until assembly" ([Cherry Blossom](https://www.trycherryblossom.com/blog/gpt-6-astra-pcb-design)) | Real part data for every footprint; footprint vs MPN/datasheet check |
| Library aliasing | Shared `C0603` names merged in EasyEDA's cache: 50 pad-association mismatches over 120 pads, all nets reading correct ([JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-easyeda-pro)) | Unique footprint names; library-identity uniqueness check |
| Missing connections despite API success | 6 missing GNDs found by pin read-back (JLCPCB EasyEDA case -> [field-reports.md](field-reports.md#end-to-end-case-studies)); unwired parts (atomic14 [S]) | Read-back netlist, pin-by-pin diff |
| Label collision shorts | ISENSE shorted to ISET; ERC only warned ([JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code)) | Pin-for-pin netlist comparison against the spec |
| Rotation and coordinate math [S] | Textbook-matrix bug (mcp-server-kicad #59); `move_footprint(rotation)` left pad/text angles stale (#110 → one orientation helper, #125); schematic-sync angles (kicad-mcp-pro #1319); keepouts in local coordinates (#128); LLM inverse rotations for labels (Copperhead #398). nexatech: "pad angles in the board file are absolute" (201/1,763 wrong, "and the gate still passed"); "Flip… is a mirror in Y plus 180°"; "where pad 1 goes under rotation is measured, not derived". Math -> [../kicad/transform-math-pitfalls.md](../kicad/transform-math-pitfalls.md) | One shared orientation helper through KiCad's own code |
| Data loss on edit [S] | kicad-python orientation setter rebuilt footprints, dropped 3D models, text boxes, dimensions (KiCAD-MCP-Server #422; kicad-mcp-pro #1321) | Preserve-all transforms; observed-diff read-back |
| State divergence | A scorer read the saved file while KiCad held live moves, hiding a ~4.0 mm² courtyard overlap (Konnect #595/#628/#648 [S]). `SaveBoard` silently changed a via's net ("three hours went into 'the router can't see its via'"). pcb-rnd `SaveTo` produced 5 copper layers ([tinycomputers](https://tinycomputers.io/posts/what-routing-314-nets-taught-me-about-ai-assisted-pcb-design.html)). An ERC count quoted from a log 58 s older than the last save | Judge the live board and report the source; input fingerprints on gate verdicts |
| Writes and checks that lie | "A write that didn't happen reports success" ("widened 36 segments", none changed: `0.15` vs `0.1500`). "A check that didn't run reports zero" (6 silent-clean cases). A `--severity-error` filter hid 20 hole_to_hole items, 19 below the fab minimum ([nexatech](https://raw.githubusercontent.com/nexatech-ltd/kicad-agent-toolkit/main/docs/lessons-learned.md)) | Checked / defect / not-checked states; diff after write |
| Checks that disagree with KiCad [S] | Single-AABB courtyard false overlaps (KiCAD-MCP-Server #406); pad-bbox fallback warnings (kicad-tools #4227); `check_clearance` measured anchor distance (Konnect #528); pcb-rnd 121 false-positive clearance flags at same-net junctions (~6 h) | Never re-implement approximations; use kicad-cli; compare several DRC tools; fab DFM as truth |
| Fab rules not configured [S] | Freerouting used 0.2 mm default instead of hole edge clearance (#419); traces through mounting holes via `::1` suffixes (freerouting #951); necking to 0.15 mm → 22 DRC; multithreaded optimizer violations → `-mt 1` (kicad-cli #32); Claude's A* router at 0.35 vs 0.5 mm edge clearance | Fab-specific rules as precondition; Freerouting `-mt 1` |
| Muted checks | "Zero violations" with 5 DRC + 4 ERC categories ignored ([JLCPCB Astra](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad)); ERC 0/0 while MCU VCAP pins floated ([Adom](https://wiki.adom.inc/api/pages/adom/kicad-board-audit/files/README.md)) | Every clean report lists disabled categories; read silenced-rule config |
| ERC/DRC-blind defects | Floating VCAP pins, supply pins tied to GND, wrong-variant VFB dividers, missing pull-ups, crystal load caps (Adom). GUI F8 found transistor pin mismatches ERC, DRC and parity all missed (nexatech). "Topology isn't values": mode resistors must cite the datasheet row | Semantic checklists; human F8 at milestones; expected-value checks |
| Ugly or weak layout that passes DRC | haohao ~10,000 zigzag segments → 600 ([field-reports.md](field-reports.md#long-form-tool-builder-logs)); "Front: beautiful placement… Back: horrendous tracks" (A6M-Zero); EEVblog bird's nest "would pass unnoticed by the AI, the simulator and the router alike" [S] | Readability metrics; style presets; human review |
| Mechanical issues found late | Late 1:1 paper check (haohao -> [field-reports.md](field-reports.md#long-form-tool-builder-logs)); antenna keepout and module placement (Tindie); "must be on edge" vs "nice to have" context missing (Autocuro) | 1:1 or 3D fit gate before routing; hard vs soft mechanical constraints |
| Endless loops, not stopping | Claude "happily kept trying to fix it… not as good at helping you recognize that the correct solution is to stop trying" (tinycomputers). Autofix loop ignored the "unconnected" DRC category, so unrouted boards were never re-routed (blwfish #158 [S]). A $10 cap was "all that stood between" a firmware agent and a $500 bill (StationX) | Retry caps (2–3); spend caps; recognize every category; escalate |
| Debugging interfaces the LLM can't run | "LLMs are not good at debugging interfaces they can't run" (tinycomputers, cross-tool DRC issue) | Run tools; give the LLM structured outputs |
| GUI and API connection gotchas | Second KiCad window steals the API; a modal dialog blocks all API calls; board must be open; API disabled by default (JLCPCB); `open_board` 30 s timeout on large boards (PowerLabKiCadAssistant #61 [S]); bridge killed by low memory; DRC API returns counts only; `importChanges()` needs a human click | Headless kicad-cli fallback; precondition checks |
| Scale limits | Gato513 validated only to 63 footprints; HackRF failure, crashes -> [field-reports.md](field-reports.md#long-form-tool-builder-logs) | Publish limits; per-region work |
| Unsafe automation [S] | Force-directed refiner "scrambles flagged components without converging" (Konnect #597); net-based decap guessing removed for exact refs (#638); connector filter caps mis-scored as decaps (#416); placement batch ran twice (JLCPCB) | Exact references; "applicable" only if score improves; idempotency |
| Agent input robustness [S] | Local models used wrong dict keys and placeholder paths (blwfish #143); viewer data dropped pad names, so REFDES:PIN failed (HTMLPCBViewer #90) | Input validation; include pad names |
| Non-determinism | Same request, different coordinates (KiCad Agentic MCP); computer use "may take a different path and land on a different board" | Deterministic solver given constraints; record seeds |
| Hallucinated defaults | "The most dangerous hallucination… is inheriting the internet's defaults" (NE555 at 3 V); LLMs "*loved* to give naive advice about decoupling" (JITX); part selection "uniformly bad" | Datasheet-grounded checks; label inferences |
| Placement-specific traps (nexatech) | Locked QFN pins: +10 mm board gave 136 vs 118 breaks; `declash` moved by courtyard, ignored copper (1 fixed, 59 new); simplified search and via-hiding traps -> [agent-tooling-reliability-patterns.md](agent-tooling-reliability-patterns.md#nexatech-kicad-agent-toolkit-methodology) | Exact-rule search; judge helpers by the acceptance verdict |

## Required guards [I]

1. A named check or guard per category above -> [agent-tooling-reliability-patterns.md](agent-tooling-reliability-patterns.md).
2. Semantic checker suite beyond DRC/ERC: footprint vs MPN/datasheet (pad count, pitch, body, variant); library-identity uniqueness; ratings vs net voltage and current; ERC-blind checklist; layout-quality metrics (decap distance, loop area, ampacity, return path, skew, congestion, readability).
3. A "clean" report always states what was disabled or not checked; never a bare green.
4. Escalate rather than loop: stop after 2–3 failed fixes per issue; present evidence and options.

## Open questions

- GitHub items are snippet-level (issue pages blocked).
- Cherry Blossom published no failure taxonomy for its 40 boards.
- Frequency of each failure across projects unknown.

## Sources

- [field_reports_and_ux.md § 1A, § 1A2, § 1C, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)
