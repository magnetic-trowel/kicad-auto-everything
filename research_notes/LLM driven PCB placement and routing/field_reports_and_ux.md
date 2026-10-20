# Field Reports of LLM/Agent-Driven PCB & EDA Work, and Human–AI Co-Design / Design-Rationale UX

> **Method and provenance (read first).** This is the second, deeper pass, done on 2026-10-20.
>
> **How sources were read:**
> - Most company blogs, case studies and HCI papers were downloaded and read in full, either as HTML-to-text or as PDF-to-text with `pdftotext`.
> - The WebFetch tool itself still could not resolve hosts, so pages were fetched with curl through the session proxy instead.
> - **github.com issue pages and the GitHub API are blocked by this session's repository policy.** GitHub issue and PR content therefore comes only from search-engine snippets of those pages. I did not attach the repositories, because the user had not asked for that. Public repository files on raw.githubusercontent.com were reachable, so the project READMEs and docs cited below are [read].
> - The shared WebSearch budget ran out again late in this pass.
> - Per coordinator instructions, forum/HN/Reddit mining is left to `practitioner_discussions.md`. Forum material here is kept short and limited to tool-design content.
>
> **Provenance tags (on every bullet):**
> - **[read]**: the primary page or paper was fetched and read in full this session.
> - **[snip]**: only search-engine summaries or snippets were seen, so verify before quoting numbers.
>
> **Evidence-type tags:**
> - **[A]**: a single-person anecdote or field report.
> - **[C]**: community discussion.
> - **[V]**: vendor or self-reported, possibly with a conflict of interest.
> - **[G]**: GitHub issue or PR (a builder's bug report).
> - **[S]**: systematic or peer-reviewed work.
>
> This file complements `llm_for_eda.md` (algorithm and paper literature). Where they overlap (GPT-6 Astra, EEBench), this file adds practitioner-level detail and corrections.

---

## 1. Field reports: what actually happens when an LLM/agent drives KiCad or other EDA tools (what worked, what broke, workarounds)

### Takeaway
By late 2026, many documented boards produced with Claude or GPT agents have been fabricated and worked on first power-up. The successes share a pattern:
- The board was simple, mostly digital, and 2–4 layers.
- The LLM orchestrated deterministic engines (Freerouting, KiCadRoutingTools, a script it wrote, or a vendor router) instead of pushing copper itself.
- KiCad's ERC/DRC plus an extra netlist read-back or parity check were fed back to the model.
- A human or a fab DFM check caught the residual errors.

The same failures recur across independent reports:
- wrong footprint variants and invented packages;
- missing connections, including ones the API reported as successful;
- rotation and coordinate math errors;
- fab rules never configured;
- ugly or weak placement and routing that still passes DRC;
- GUI-level operation that is slow and non-reproducible;
- LLM debugging loops that never terminate.

The workarounds are just as consistent:
- work code-first or through the API;
- use deterministic solvers for geometry;
- add staged gates with independent read-back verification;
- start read-only and confine edits to a Git sandbox;
- treat the fab's DFM as an external oracle;
- have a human step in at defined checkpoints.

### Cited Findings

**A. End-to-end case studies (read in full)**

- **A6M-Zero, "This PCB is brought to you by Fable 5" (Sept 4, 2026) [read][A].**
  - **Earlier attempt:** the author first tried "a dead simple PCB with Claude Opus 4.8 and it was terrible! It had no idea about the orientation of the components, it did not do any proper routing."
  - **Fable 5 run:** working through a KiCad MCP server, Fable 5 "worked autonomously for a couple of hours." Rules: no manual edits or verification; every problem goes back to the model.
  - **Prompt:** five lines naming an RP2350, four Watchy buttons, a GDEY0154D67 e-ink display, board size equal to the display, I²C and GPIO breakout, and "use the kicad mcp."
  - **Result:** 65 footprints, 54 nets, 118 unconnected lines, and **65 DRC errors** on the first pass, which were simply reported back to Fable. The author describes the "Front: beautiful placement, with two mistakes / Back: horrendous tracks."
  - **Footprint errors:** a W25Q128JVS (SOIC-8 wide) on SOP-8 pads, and a boost-converter transistor whose package was too small for its pads. They were noticed only at the JLCPCB upload preview. **"For the W25Q128JVS it insisted that there was a SOP-8 package but I could not find it in LCSC's library."** The flash was swapped for a P25Q64SH.
  - **Routing:** Freerouting "plateaued at sixty nine connections, leaving 49 disconnected," and Claude hand-routed the rest. KiCadRoutingTools later routed all of them in 1.25 s.
  - **Outcome:** 4 layers, 31.8 × 37.32 mm, €130 for 5 assembled boards. It enumerated over USB on first plug-in.
  - **Author's feeling:** "Great and meh… I was not feeling much of an accomplishment." The next project uses Fable 5.1 with KiCadRoutingTools from the start.
  - Sources: [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/); [Adafruit coverage](https://blog.adafruit.com/2026/09/15/this-pcb-is-brought-to-you-by-fable-5-a6m-zero) [snip]
- **tinycomputers.io, "What Routing 314 Nets Taught Me About AI-Assisted PCB Design" (GigaShield v0.4, 2026) [read][A].** This is the most candid long-form report found.
  - **Board:** 155 × 90 mm, ten SN74LVC8T245 shifters translating 72 channels. It is generated entirely by a Python script emitting a pcb-rnd file, "no schematic… no graphical layout," then routed by Freerouting. An earlier v0.3 board failed from a dual-row-header pin-numbering convention bug: "the fabricated board was perfect; the design was wrong."
  - **Bug class 1, caught easily:** a datasheet-cross-referencing audit, about 15 minutes, found a DIR pulldown that would power a shifter up in the wrong direction. **"I didn't write that code. Claude Code did, three weeks earlier… The wrong comment and the wrong pulldown direction were both introduced by the same LLM that later caught the mistake on audit."**
  - **Bug class 2, no help at all:** pcb-rnd DRC reported 121 clearance violations that never changed with Freerouting settings. They were all **false positives at same-net trace–pad junctions**, while PCBWay's DFM flagged real near-misses, including one D=0 spot. It took about 6 hours. **"LLMs are not good at debugging interfaces they can't run."**
  - **Bug class 3, made worse:** pcb-rnd's `SaveTo` rewrote the layer `Groups()` string and produced 5 copper layers. "Claude Code happily kept trying to fix it… it's not as good at helping you recognize that the correct solution is to stop trying." The fix was to revert and delete empty Gerbers, after about 2 hours.
  - **Placement win:** after a failed 4-layer route, Claude noted "the unrouted nets all terminated in the same congested region" and asked about staggering U6–U10 into two columns. The result was **314/314 nets routed on 4 layers**. "The LLM didn't solve a geometric problem I couldn't solve. It pointed at a geometric problem I hadn't recognized as a problem."
  - **Indispensable for:** parsing hierarchical S-expressions, generating footprint code from datasheets (it got the TSSOP-24 B-side reversed pin order right), file-format debugging, and the SSH tool shuffle.
  - **Not helpful for:** cross-tool interaction bugs, physical-intuition placement decisions, and knowing when to stop.
  - **Cost:** about 18 hours of engineering time.
  - **Lessons:** dry-run the pipeline on a toy board; run DRC with several tools and compare; treat the fab DFM as the source of truth; unit-test the generator ("net X has pins Y and Z"); and "when a fix doesn't work on the second or third try, that's the signal to stop."
  - **Verdict:** "a competent junior collaborator with encyclopedic memory, infinite patience, and no physical intuition."
  - Sources: [tinycomputers 314 nets](https://tinycomputers.io/posts/what-routing-314-nets-taught-me-about-ai-assisted-pcb-design.html); [Part 1](https://tinycomputers.io/posts/redesigning-a-pcb-with-claude-code-and-open-source-eda-part-1.html) [snip]
- **JLCPCB, "KiCad MCP: Design a PCB with Claude Code in KiCad 10" (Oct 14, 2026) [read][V/A].**
  - **Setup:** an XL4015 5 A buck converter with a 16-net netlist, on a 63 × 33 mm, 2-layer board, built with **kicad-mcp-pro**, chosen because its read-only default limits what an AI error can change.
  - **Design-review fixes before any schematic existed:** VC pin wrongly tied to GND, a 78L05 rated 30 V against a 36 V input, a 1.25 W single shunt, and 35 V bulk caps.
  - **Seven AI or server issues, each caught by a check:**
    - auto-layout stacked all three LM358 units on top of each other;
    - the server could not wire multi-unit parts (fixed with a 9-line patch);
    - **an overlapping-label collision shorted ISENSE to ISET, and ERC only warned** (caught by a pin-for-pin netlist comparison);
    - the FB trace was routed beside the SW node (fixed with a 1.2 mm analog keepout);
    - **the server had no autorouter, so Claude wrote its own A* grid router (0.1 mm grid)**, which used a 0.35 mm edge clearance against a 0.5 mm rule and caused 7 DRC errors;
    - the server's part search was unreliable (replaced by a direct JLCPCB parts query);
    - **a placement batch ran twice**, drawing the board outline twice.
  - **Placement method:** planned offline with a script that checked overlaps and rendered a ratsnest preview, then applied live with `pcb_move_footprint`.
  - **Silkscreen:** a label-placement script took warnings from 47 to 2.
  - **Connection gotchas:** a second KiCad window steals the API; **a modal dialog blocks all API calls**; the PCB Editor must have the board open; the API is disabled by default.
  - **Closing note:** "Zero DRC errors mean the layout meets its rules. It does not confirm that the schematic matches your intent."
  - Sources: [JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code); [kicad-mcp-pro #1314 reproduces it](https://github.com/oaslananka/kicad-mcp-pro/issues/1314) [snip]
- **JLCPCB, "Claude Code PCB Design: Can It Build a Real Board in EasyEDA Pro?" (2026) [read][V/A].**
  - **Setup:** Claude Opus 5.5 with the official EasyEDA API skill: an API reference covering ~120 classes, 62 enums and 70 interfaces "so the model looks up real method signatures instead of guessing them", plus a local bridge server, with a 30 s timeout per call.
  - **Result:** a 47-part, 3-page schematic rebuilt from a PDF and a CONNECTIONS.md pin map, then a 2-layer, 71.1 × 50.8 mm board with 33/33 nets and 0 DRC.
  - **API failures:**
    - **"A successful API response doesn't always mean the design is correct."** Reading back the netlist verified 138/138 pins and **found six missing GND connections**.
    - Parts placed via the API silently lost supplier attributes, and a name-only `modify()` broke them again.
    - Netlist export hung, so the netlist was rebuilt from read-back data.
    - **The DRC API returns counts only, not locations**, so a human pasted the DRC log.
    - `importChanges()` waits for a human "Apply" click.
    - The bridge was killed twice by low memory.
  - **Placement and routing:** placement came from written zone rules plus a scripted pad-pair check, which found one overlap. Routing used Freerouting headless with `-mt 1`, a `check_ses.py` script that must report "open nets 0", and vias imported before tracks.
  - **Human approval:** the human approved all 8 stock substitutions.
  - **What Claude could not do:** "Claude Code did not directly see the PCB layout." Visual review, 3D clearance, thermal, footprint and datasheet checks stayed with the human.
  - **Open items:** SW3 slide-switch contact layout, USB-C edge overhang, and battery polarity "because the source PDF was ambiguous."
  - Source: [JLCPCB](https://jlcpcb.com/blog/claude-code-pcb-design)
- **JLCPCB, "GPT-6 Astra PCB Design in KiCad: From Brief to Verified Native Project" [read][V/A].**
  - **Setup:** a TPA3116D2 amplifier from a 4-line brief, with 45 footprint instances and 120 pads.
  - **Workflow:** "Define and lock the critical supply, bootstrap, and switching copper first. Let the autorouter finish the low-current nets, then refill the zones and confirm the locked copper survived."
  - **Parity:** **46 schematic-parity issues**, mostly missing Manufacturer and Rating fields plus the intentional SYNC no-connect. They were fixed in source data, "not by adding rule exclusions."
  - **"Zero violations" was qualified:** 5 DRC and 4 ERC categories were ignored, "so those nine ignored categories are therefore part of the result."
  - **Independent check:** all 120 pin-to-pad pairs were compared against the saved spec, because "two files can match and still share the same mistake."
  - **Portability:** the project was copied to a fresh directory and the checks re-run.
  - **Tooling:** the app-launch request timed out, so checks ran via kicad-cli.
  - **FAQ caveat:** the routed layout **"came from an earlier amplifier task and was reused unchanged"**, so this article does not show Astra routing that board.
  - Source: [JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad)
- **JLCPCB, GPT-6 Astra in EasyEDA Pro [read][V/A].**
  - **Clarification:** Astra asked one clarifying question, the speaker impedance, before drawing.
  - **Routing:** KiCad 10 held the routed master, and Freerouting 2.0.1 routed the low-current nets after critical copper was locked.
  - **Import failure:** the first import "opened cleanly and looked plausible", yet produced **50 association mismatches over 120 pads**. Shared library names like `C0603` merged in EasyEDA's device cache and "quietly swap pad orientations", even though all 120 pad nets read correct. Renaming footprints uniquely (e.g. `C0603_C12`) fixed it.
  - Source: [JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-easyeda-pro)
- **NextPCB, "Can GPT-6 Astra Automate PCB Routing?" (Hubert Hu, Head of Technology) [read][A].**
  - **Same board, placement fixed:**
    - Test 1 (unrestricted): ~12 min, done via **DSN → Freerouting → SES**. "Freerouting performed the core routing computation. Astra orchestrated the workflow."
    - Test 2 (GUI only, no external tools): **after one hour, "only three short trace segments."**
  - **Framing quote:** "The AI clicked the button. The router solved the routing problem… Calling an autorouter is not the same as becoming one."
  - **Funding concern:** the author worries the demo will be misread by investors and undercut funding for specialist routing research.
  - **Caveat:** two runs on one board.
  - Source: [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test)
- **Tindie Blog, gongyu (Sept 8, 2026) [read][A].**
  - **Inputs:** an ESP32-S31 robot-head board, built from two Espressif reference PDFs, a short description and a concept image.
  - **GPT-5.6 (chat):** the schematic was "hard to read" with non-standard symbols until it was asked to redraw with KiCad library symbols.
  - **GPT-6 Astra (Work mode, ~3 iterations):**
    - a complete KiCad 7+ project with a 13-block hierarchical schematic, official-library symbols and most 3D models;
    - **9 unrouted nets**;
    - antenna keep-out and placement around the module "still need improvement."
  - **Author's estimate:** it would save "well over half" of initial-design time. He calls today's workflow "essentially open-loop" and argues that closing the loop (simulation, ERC/DRC, SI/PI, DFM, BOM) is the next step.
  - Source: [Tindie](https://blog.tindie.com/2026/09/i-designed-a-kicad-pcb-with-gpt-5-6-and-gpt-6-and-it-changed-how-i-think-about-hardware-design/)
- **StationX, "AI PCB Design: My AI Tried to Make Itself Physical" (Nathan House, July 2026) [read][A].**
  - **Agent:** "HAL", with a terminal, KiCad 10 and a validation pipeline, building a 555 blinky badge in under 1 hour.
  - **Error log, written by the agent itself:**
    - rejected the canonical NE555 because it won't run at 3 V and used a TLC555 ("the most dangerous hallucination… is inheriting the internet's defaults");
    - **placed a via 0.0285 mm from an LED pad: "I had verified the clearance against one pad and forgotten its neighbour"**;
    - violated courtyards twice: **"I have no spatial intuition, only arithmetic, and where I skipped the arithmetic I failed"**;
    - reported an impossible 150.4% duty cycle from a mis-built simulation measurement;
    - could find no sourced battery-holder polarity, so it inferred it from construction and **"logged that reasoning as reasoning, not as a sourced fact."**
  - **Author's maxims:** "trusted because the tools stopped objecting"; "keep the AI's inferences labelled as inferences, or the workflow starts laundering guesses into 'facts'"; "give it zero discretion in verification"; save lessons into a skills file.
  - **Altium Academy head-to-head:** StationX cites a 2026 Altium Academy video comparing a human and an AI layout tool on the same schematic: **168 DRC violations for the AI vs 0 for the human**. This number refers to that video, not to the StationX build.
  - Sources: [StationX](https://app.stationx.net/articles/ai-pcb-design); [Altium Academy video](https://www.youtube.com/watch?v=qX29OWSYTmI) (not watched)
- **MakeUseOf (Aug 21, 2026), Claude Code with the mixelpixx KiCAD-MCP [read][A].**
  - Natural-language operations worked well: board outline with corner radius, mounting holes, LED grid arrays, align/distribute, net classes, DRC.
  - **Limits:** rate limits on a $20 Pro plan; **"Claude will get the component footprints wrong from time to time"**; and you need KiCad vocabulary to ask for the right things.
  - Source: [MakeUseOf](https://www.makeuseof.com/pcb-design-easier-thanks-to-claude/)
- **KiCad Agentic MCP announcement (nevenfo, Aug 27, 2026) [read][A/C].**
  - **Tool design:** "I did not want the AI itself deciding that a PCB was correct. KiCad does the verification." If ERC/DRC cannot run, the tool reports an error "instead of pretending the board is clean." Edits go through the IPC API, so Ctrl+Z works.
  - **Reproducible demo:** a regulator plus 2 caps, run twice, went from 5 unconnected items to 0 each time, but **"the exact coordinates were different between the two runs."**
  - **Speed:** **the KiCad operations take under 1 s; the full AI interaction takes about 6–7 min.**
  - **First community reply:** "I would have done a better layout for these three components faster than typing that prompt."
  - Source: [KiCad forum thread (via Discourse JSON)](https://forum.kicad.info/t/kicad-agentic-mcp-an-ai-assistant-that-edits-your-board-through-kicads-own-api-and-lets-kicad-decide-whether-the-result-is-good/71403)
- **atomic14 (July 2025) [snip][A].** Claude Code (better than Cursor) with atopile produced an ESP32-S3 board. The first build left components unwired, and the EN RC was missing its capacitor. Layout was done in KiCad by hand. — [atomic14](https://atomic14.substack.com/p/vibe-coding-a-pcb-surprisingly-good)

**B. "Computer use" versus API/scripting**

- I still found **no documented Claude computer-use experiment that places or routes in the KiCad GUI**.
- The only controlled GUI-only data point is NextPCB's: 3 segments per hour. — [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test) [read]
- JLCPCB notes that computer use makes the model "a user of KiCad because it lacks its own routing engine and design rule checker." — [JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad) [read]
- **A vendor-authored map (PCBEditor):**
  - Computer use "is the slowest possible path… It is also not reproducible — run the same request twice and the model may take a different path and land on a different board. For hardware, that last point is usually disqualifying."
  - "When an AI triggers KiCad's autorouter, KiCad routes the board."
  - Python scripting with an assistant is "the most underrated option, by a distance."
  - [read][V] — [DEV Community](https://dev.to/dibyaprakash_pradhan/kicad-and-ai-in-2026-mcp-servers-scripts-and-what-actually-works-3p1a)
- **EEBench authors:** an agent operating a GUI CAD tool "spends a lot of time clicking around and keeping track of what is on screen. A lot of its context consists of coordinates, menus and application state." [read][V] — [EEBench blog](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)

**C. Bugs reported by KiCad-MCP builders [snip][G]** (GitHub could not be opened directly; these come from search snippets of the issue pages.)

- **Rotation and orientation math:**
  - The textbook rotation matrix was used where KiCad uses the transpose, so footprints came back mirrored. — [mcp-server-kicad PR #59](https://github.com/ProductOfAmerica/mcp-server-kicad/pull/59)
  - `move_footprint(rotation=r)` rewrote only the footprint's `(at)`, leaving pad and text angles stale, so "copper is drawn rotated against the body". — [issue #110](https://github.com/ProductOfAmerica/mcp-server-kicad/issues/110); fixed by one orientation helper in [PR #125](https://github.com/ProductOfAmerica/mcp-server-kicad/pull/125)
  - Pad and field angles were not rotated on schematic sync. — [kicad-mcp-pro #1319](https://github.com/oaslananka/kicad-mcp-pro/issues/1319)
  - A footprint swap wrote embedded antenna keepouts in local coordinates. — [mcp-server-kicad #128](https://github.com/ProductOfAmerica/mcp-server-kicad/issues/128)
- **Data loss on edit:** rotating through kicad-python's orientation setter rebuilt the footprint and **dropped its 3D models**, and also text boxes and dimensions. — [KiCAD-MCP-Server PR #422](https://github.com/mixelpixx/KiCAD-MCP-Server/pull/422); [kicad-mcp-pro #1321](https://github.com/oaslananka/kicad-mcp-pro/issues/1321)
- **Checks that disagree with KiCad:**
  - Single-AABB courtyard checks flagged false overlaps. — [KiCAD-MCP-Server #406](https://github.com/mixelpixx/KiCAD-MCP-Server/issues/406)
  - A pad-bbox fallback produced misleading "courtyard_overlap" warnings. — [kicad-tools #4227](https://github.com/rjwalters/kicad-tools/issues/4227)
  - **The placement scorer read the saved .kicad_pcb while KiCad held unsaved live moves, hiding a real ~4.0 mm² courtyard overlap.** The fix prefers the live board and "reports which source it judged". — [Konnect #595](https://github.com/mixelpixx/Konnect/issues/595); [PR #628](https://github.com/mixelpixx/Konnect/pull/628); [PR #648](https://github.com/mixelpixx/Konnect/pull/648)
  - `check_clearance` actually measured anchor distance, so its documentation was corrected to say so. — [Konnect PR #528](https://github.com/mixelpixx/Konnect/pull/528)
- **Unsafe automation:**
  - A force-directed refiner "scrambles flagged components without converging or improving the score", proposing moves of tens of mm. — [Konnect #597](https://github.com/mixelpixx/Konnect/issues/597)
  - **Net-based guessing of which capacitors are decoupling caps was removed: exact references are now required, and a plan reports "applicable" only if every target lands inside the outline and the score improves.** — [Konnect PR #638](https://github.com/mixelpixx/Konnect/pull/638)
  - Planners now refuse boards whose outline can't be verified as a rectangle. — [Konnect PR #684](https://github.com/mixelpixx/Konnect/pull/684)
  - Connector filter caps were mis-scored as decoupling defects. — [Konnect PR #416](https://github.com/mixelpixx/Konnect/pull/416)
- **Missing operations:** no tool moves Reference/Value text. — [Konnect #829](https://github.com/mixelpixx/Konnect/issues/829). LLMs got inverse rotations wrong when asked to place labels, so board-coordinate label placement was added. — [Copperhead PR #398](https://github.com/copperheadhq/copperhead/pull/398)
- **Autorouter integration:**
  - Freerouting tracks used the 0.2 mm default instead of the hole edge clearance. — [KiCAD-MCP-Server PR #419](https://github.com/mixelpixx/KiCAD-MCP-Server/pull/419)
  - Traces were routed through mounting holes because of footprint `::1` suffixes. — [freerouting #951](https://github.com/freerouting/freerouting/issues/951)
  - Freerouting necked tracks to 0.15 mm, below the board minimum, causing 22 DRC errors. Its multithreaded optimizer causes clearance violations, so `-mt 1` is used. — [fatecannotbealtered/kicad-cli PR #32](https://github.com/fatecannotbealtered/kicad-cli/pull/32)
  - **An autofix loop did not recognize the "unconnected" DRC category, so boards whose only problem was unrouted nets were never re-routed.** — [blwfish/kicad-mcp PR #158](https://github.com/blwfish/kicad-mcp/pull/158)
- **Agent input robustness:** local models called tools with wrong dictionary keys and placeholder paths, so validation was added. — [blwfish/kicad-mcp PR #143](https://github.com/blwfish/kicad-mcp/pull/143). Viewer data dropped pad names, so agents could not map REFDES:PIN. — [HTMLPCBViewer #90](https://github.com/Gherkin/HTMLPCBViewer/issues/90)
- **Scale:**
  - List results are capped with `_total` and `_truncated` metadata, and narrow per-list tools are recommended. — [havamal-65/KiCad-MCP](https://github.com/havamal-65/KiCad-MCP)
  - A compact board-state encoding was validated to 63 footprints, but **the autorouter did not complete on a 437-footprint 4-layer board**. — [Gato513/kicad-mcp](https://github.com/Gato513/kicad-mcp)
  - A 30 s `open_board` timeout was hit on a large board. — [PowerLabKiCadAssistant #61](https://github.com/odtu/PowerLabKiCadAssistant/issues/61)
- **Transactions and undo:**
  - Native IPC commit groups make one multi-step agent edit a single KiCad undo step (tested on KiCad 10.0.5). — [kicad-mcp-pro #728](https://github.com/oaslananka/kicad-mcp-pro/issues/728); [PR #808](https://github.com/oaslananka/kicad-mcp-pro/pull/808)
  - Schematic creates are chunked inside one commit, so one Undo restores the prior state. — [Konnect PR #752](https://github.com/mixelpixx/Konnect/pull/752)
  - File-level before-images are used for rollback. — [kicad-agentic-mcp](https://github.com/nevenfo/kicad-agentic-mcp)
- **Explicit AI/deterministic boundary (CopperMCP):** "AI may interpret constraints and propose net ordering, corridors, cost weights, and repairs. Deterministic code owns geometry, connectivity, DRC, provenance, and file mutation." Generated work stays "an immutable candidate until a user validates and explicitly applies it," and route previews have "no apply path." — [Glama listing](https://glama.ai/mcp/servers/seunghyukchoe/copper-mcp). Copperhead uses a similar rule: nothing touches a file until a validated change proposal exists. — [everydev](https://www.everydev.ai/tools/copperhead/llms.txt)

**D. Commercial AI layout tools in the field (read in full unless marked)**

- **Flux AI Auto-Layout [read][V].**
  - **Dec 2024 preview:** RL-based, "you can watch the layout improve over multiple iterations and accept or cancel at any point"; runs take minutes to hours.
  - **Summer 2025:**
    - **net types in 7 priority buckets** (High Speed, Analog, Power, Medium, Low, Uncertain, Ground); Flux infers them and "you can check and change the inference";
    - "relaxed clearance" that trades length for cleaner, more manufacturable looks;
    - protected polygons smaller than 10% of board area;
    - suggested workflows: full-board, hybrid (pre-route critical nets), and "Placement Check: run Auto-Layout early to catch crowded components."
  - **Winter 2025:** "not designed to fully autoroute every class of board"; a preparation checklist (realistic rulesets, keepouts, fan out fine-pitch parts, hand-route critical nets); the run **stops when further search is unlikely to improve**; credits from about 375 to 1,250 per board.
  - **AI Design Reviews:** "blend deterministic algorithms with AI"; **"The system always explains why an issue was flagged"**; ❌/⚠️/✅ statuses with click-to-navigate; example: "C3 has a voltage rating of 16V, which is less than the required 50V."
  - **Gap Flux itself admits (via StationX):** the copilot "does not have full context on component positioning or PCB routing."
  - Sources: [intro](https://www.flux.ai/p/blog/introducing-ai-auto-layout); [summer](https://www.flux.ai/p/blog/ai-auto-layout-just-got-smarter); [winter](https://www.flux.ai/p/blog/ai-auto-layout-winter-update); [design review](https://www.flux.ai/p/blog/introducing-the-ai-design-review-tab); [StationX](https://app.stationx.net/articles/ai-pcb-design)
- **Quilter [read][V].**
  - **Positioning:**
    - "Connecting pins is not the same as producing a board an engineer can trust."
    - Placement and routing are treated as one coupled problem.
    - It uses RL, solvers and computational geometry, with **Physics Rule Checks** run during candidate generation.
    - It produces "dozens to hundreds of ranked candidates," whereas an LLM session produces one result.
  - **Aesthetics:** designers call layout "artwork"; "a tool that ignores it produces output engineers reject on sight… What 'looks right' varies by company, by team, sometimes by individual reviewer."
  - **Control:** "Everything already placed or routed… Quilter treats as 'solved'." It "provides output that helps engineers understand which identified constraints were met and which still need attention… AI layout should not be a black box."
  - **Sweet spot:** 100–1,000 components, pin density under 20%, up to about 10 GHz, through-hole vias. BGA fanouts, length matching and RF are still in development.
  - **Project Speedrun:** 428 h quoted for manual layout versus 38.5 h of human cleanup, plus 27 h of automated layout. Cleanup was "a precision pass": bigger power pours "for comfort," length tuning redone because the engine ignored via delay, and power nets made more conservative "to match human comfort levels."
  - **Snippet-only claims:** engineers review "how constraints are interpreted" before submitting, and boards go through 2–5 review cycles [snip].
  - **On LLMs:** Quilter quotes its engineer Fayaz Rahman: "Router is very sequential… we can't do some sort of backtracking."
  - Sources: [Quilter LLM post](https://www.quilter.ai/blog/llm-pcb-layout-gpt-6-astra); [autorouter post](https://www.quilter.ai/blog/pcb-autorouter-was-the-right-idea); [cleanup](https://www.quilter.ai/blog/cleaning-up-an-ai-designed-computer); [snip: AAC](https://www.allaboutcircuits.com/news/for-the-first-time-ai-designs-computerin-less-than-a-week/)
- **DeepPCB [read][V].**
  - **"The autorouter broke your trust" post:**
    - Fixed heuristic priority orderings fail because "the optimal priority ordering changes… from region to region."
    - Engineers "spend nearly as much time configuring the autorouter constraints as you would have spent routing manually… debugging the autorouter's interpretation of your rules."
    - **"[RL systems] can't explain their reasoning… For verification and debugging, this opacity is a genuine limitation."**
    - RL systems are "interpolation engines," so ask vendors about their training distribution.
    - The value is the 80/20 split: automate the routine 80% and keep human attention on the critical 20%.
  - **Vendor benchmark on 3 open-source boards (98, 290 and 414 airwires):** DeepPCB averaged 97.3% completion versus Quilter's 87.7%, Quilter used 44% more vias, and DeepPCB returned its first result in 1–2 min versus 15–20 min.
  - **Correction to pass 1:** the "414-net board: DeepPCB left 12, Quilter 54" figure I previously attributed to an independent DEV post matches this vendor benchmark exactly, so it is likely derivative.
  - Sources: [DeepPCB trust](https://deeppcb.ai/the-autorouter-broke-your-trust-heres-whats-actually-different-now/); [DeepPCB vs Quilter](https://deeppcb.ai/deeppcb-vs-quilter-open-source-routing-compared-2026/); [DEV/AnyPCBA](https://dev.to/anypcba_official/i-let-ai-design-a-pcb-heres-how-it-went-5e41) [snip]
- **Diode Computers [read][V].**
  - **Partnership post:** Diode works with Anthropic using **Zener**, a Starlark DSL. A pipeline (datasheet plus examples, then an LLM draft, then programmatic checks, with critical issues fed back, then human review) produced **about 250 reference designs in two weeks**.
  - **Registry:** modules come with "a validated layout fragment… what remains is largely inter module routing."
  - **Checks:** SPICE results serve as "ground truth."
  - **Layout:** Claude parses KiCad boards to propose decap placement near pins, bank bulk caps and align labels. "Any proposal from a model arrives as a clear, reviewable diff."
  - **Timeline:** layout and human review "remain the final stages," with projects shrinking "from months to weeks."
  - **Reviewer post:** a read-only AI reviewer found 22 bugs in comma.ai's challenge and won the $1000 prize. Principles: "it should not invent findings. If there is no evidence, there is no report"; "A bad AI reviewer is worse than no reviewer… now an engineer has to review the review"; reviewing means "reconstructing the intent of the engineer," and "intent lives outside the file."
  - **Unverified:** the claim that Diode's engineers preferred Sonnet 4.5 reference designs 8/10 times appeared only in a search summary [snip].
  - Sources: [Diode × Anthropic](https://blog.diode.computer/anthropic-partnership); [Diode reviewer](https://blog.diode.computer/hardware-review)
- **Cherry Blossom [read][V]:** see §2.
- **tscircuit [read][V]:**
  - **Docs:** the recommended prompt structure ends with: "First create a complete, readable placement and netlist. Then run `tsci check placement`, inspect the PCB image, and fix overlaps or missing connections before enabling routing." The docs suggest concrete follow-ups such as `tsci build --pcb-png`, "It is extremely sparse right now; try to pack it more tightly," and one focused correction at a time.
  - **Seve Ibarluzea on packing:** "Sequential Optimal Packing" is a deterministic, legible placement method in which "every individual packing decision is easy to understand." Its weaknesses (pack order, local optima) are mitigated by "hardening" constraints, and "LLM loops can easily adapt the design intent representation to do this!"
  - Sources: [tscircuit AI docs](https://docs.tscircuit.com/guides/circuit-generation/generating-circuit-boards-with-ai); [autorouting blog](https://blog.autorouting.com/p/sequential-optimal-packing-for-pcb)
- **Adafruit vs Flux [unverified]:** a third-party page claims Flux's counsel sent Adafruit a demand letter (June 1, 2026) over a planned review. The Adafruit page returned 403, so I could not confirm it. — [qwe.edu.pl](https://www.qwe.edu.pl/tutorial/adafruit-flux-ai-demand-letter-evaluate-ai-pcb-tools/) [snip]

**E. Practitioner sentiment, condensed (full forum mining is in `practitioner_discussions.md`)**

- EEVblog [snip][C]: Claude helps most with review and checking (a swapped IC pin, renumbering about 1,200 parts) rather than layout. A bird's-nest routing "would pass unnoticed by the AI, the simulator and the router alike." — [EEVblog](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/)
- KiCad forum, Astra thread [snip][C]: "like routing a board by describing it through text to an intern who has never used ECAD"; placement is "the hard problem"; "give it deterministic tools to orchestrate." — [KiCad forum](https://forum.kicad.info/t/open-ai-claims-gpt-6-astra-can-make-pcb-boards/71487)
- A Hackaday commenter ("Em") vibe-coded three PCBs that all worked on the first spin; "the routing can look a little wonky (which started me down the rabbit hole of making a rust fork of freerouting)." — [zerowithdot, quoting Hackaday](https://zerowithdot.com/blog/gpt-6-astra-impact-on-cad/) [read]

### Inferences
- The pattern that works is clear: **the LLM handles intent, code and orchestration; deterministic engines handle geometry; KiCad and the fab handle the verdict; and independent read-back confirms what was actually written.** Every report where the LLM pushed copper directly (GUI routing, hand-routing leftovers, label math, a self-written grid router) shows slow progress or geometric errors.
- **"The API said OK" is not evidence.** EasyEDA calls returned success while dropping 6 GND connections and attributes. kicad-python rotations silently dropped 3D models. A placement batch ran twice. A tool therefore needs post-write read-back diffs as a first-class feature.
- The costliest failures are **invisible to DRC/ERC**: package variants, same-name footprint aliasing, label-collision shorts that ERC only warns about, ratings, and muted rule categories. Ground truth must include semantic and parity checks, and a "clean" report must state what was disabled.
- Many failures are **tool bugs**. If tool geometry, checks or state (saved file versus live board) diverge from KiCad's, the agent chases phantom errors or misses real ones.
- LLM agents run into the same kind of problem as unbounded autorouter runs: endless fix loops (tinycomputers; ESP32 firmware agent in StationX). A loop budget and an explicit "stop and escalate" policy are required.
- **LLMs add real value at the "noticing" level.** They can say "unrouted nets cluster in one region; spread U6–U10," flag a decap that is too far away, or catch a datasheet mismatch. They are far less useful when computing exact coordinates. A placer/router should expose congestion and failure attribution to the LLM so it can make this kind of contribution.

### Gaps
- GitHub issue threads were not read in full because github.com is blocked by session policy, so §1C rests on snippets. To mine issues fully, the user would need to attach the relevant repositories (mixelpixx/KiCAD-MCP-Server, mixelpixx/Konnect, oaslananka/kicad-mcp-pro, ProductOfAmerica/mcp-server-kicad).
- I found no documented Claude computer-use KiCad GUI layout experiment.
- I could not watch the Altium Academy "168 vs 0" video, so its methodology is unknown.
- The Diode Sonnet-preference statistic and the Adafruit/Flux episode remain unverified.

---

## 2. Published evaluations and demos with quantitative results

### Takeaway
Quantitative evidence is still thin and mostly vendor-run.

**EEBench** (by atopile) is the main public leaderboard, but its V1 **deliberately excludes layout**: it grades simulated circuit design in atopile code. Frontier agents score about 55–70% there, with error bars of ±6–11 points, and the scaffold changes results substantially.

**Layout evidence** is all single-board anecdotes (unrouted counts, DRC counts, parity counts) plus vendor comparisons:
- Cherry Blossom: 40 boards behind a verification gate.
- Quilter: Project Speedrun.
- DeepPCB: a 3-board comparison with Quilter.

PCB-Bench (ICLR 2026) evaluates LLM understanding of PCBs, not the quality of the layouts they produce. I found no independent benchmark of LLM-driven placement quality on real boards.

### Cited Findings
- **EEBench methodology [read][V/S]:**
  - "Schematic and layout barely register: most engineering happens outside the CAD, which records what simulation, calculation, and research already decided."
  - V1 targets the requirements → design → test loop; **"Layout is deliberately out of scope — sequenced, not forgotten."** V2 and later are planned to add layout, fabrication and bring-up.
  - Agents submit atopile bundles. Grading is deterministic: builds, SPICE at worst-case tolerance corners, and BOM checks, with "No human graders. No LLM-as-judge."
  - Score = **0.65 × technical + 0.35 × cost-efficiency**, and cost credit requires a working design.
  - Sources: [EEBench methodology](https://eebench.org/methodology.html); [EEBench blog](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)
- **EEBench, Sept 1, 2026 leaderboard [read]:** Claude Opus 5 61.6%, Grok 4.6 57.1%, Claude Fable 5.1 56.4%, Claude Fable 5 54.3%, Claude Opus 4.8 Max 51.4%. Example failure: a submitted 22 µF MLCC bank gave only 11.4 µF effective at 4.7 V bias against a 545 µF requirement, so the rail fell below 3 V after 0.85 ms: "The source built successfully; the circuit still failed the job." EEBench discloses: "built and funded by the team behind atopile… do not sell benchmark scores." — [EEBench blog](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)
- **EEBench, Sept 4 table as reported by Cherry Blossom [read][V]:**

  | Model | Score | Cost per task | Time per task |
  |---|---|---|---|
  | GPT-6 Astra | 69.3 ±10.7 | $0.83 | 1m46s |
  | Claude Opus 5 | 61.6 ±6.0 | $2.38 | 13m1s |
  | Grok 4.6 | 57.1 ±9.9 | | 35m26s |
  | Fable 5.1 | 56.4 ±10.1 | | |
  | Gemini 3.8 Flash | 55.4 ±10.4 | | |

  **Conflict:** zerowithdot (Sept 10) wrote that "Astra has NO EEBench result" and quoted the EEBench blog as saying "We do not have a GPT-6 Astra result yet." The current blog text no longer contains that sentence, while Hackaday and Cherry Blossom report 69.3%. This is likely a timing or update issue, so treat Astra's score as provisional. — [Cherry Blossom](https://www.trycherryblossom.com/blog/gpt-6-astra-pcb-design); [zerowithdot](https://zerowithdot.com/blog/gpt-6-astra-impact-on-cad/); [Hackaday](https://hackaday.com/2026/09/05/can-ai-now-design-pcbs-that-just-work/) [read]
- **A later EEBench mirror snapshot [snip]:** Claude Opus 5.5 at 75.0% leading on Sept 29. The mirror has duplicate rows and gives scaffold effects (Claude Code, Codex CLI, Gemini CLI) as part of each entry. — [BenchLM](https://benchlm.ai/benchmarks/eebench)
- **Harness effects in general [read]:** ARC-AGI-3 scored 62.7% under the standard harness and 99.9% under OpenAI's harness for the same model, a 37-point gap from two undisclosed API settings. The same article notes that BenchCAD CAD scores are vendor self-reported and that a part with 96.1% geometric similarity was still faulty. — [zerowithdot](https://zerowithdot.com/blog/gpt-6-astra-impact-on-cad/)
- **Cherry Blossom, 40 boards [read][V]:**
  - **Setup:** GPT-6 Astra on "drones, robotics and sensors," inside "real part data for footprints, and a verification gate on every AI edit."
  - **Results:** **first-pass fab yield 94% → 97%** and **design time −54%** compared with their prior model tier.
  - **Interpretation:** "The same model scores 69.3% designing circuits on its own and produces boards that come back working 97% of the time once real part data and a verification gate are wrapped around it."
  - **Four hurdles:** netlist correctness, real parts and footprints ("Invented footprints are the most expensive failure… nothing catches them until assembly"), placement and routing ("the one that was already closest to solved"), and manufacturability.
  - **Caveat in their own words:** "Forty boards is our own sample… a reason to keep testing it, not a reason to ship it."
  - Source: [Cherry Blossom](https://www.trycherryblossom.com/blog/gpt-6-astra-pcb-design)
- **Quilter Project Speedrun [read][V]:** an 8-layer i.MX 8M Mini computer quoted at 428 h for manual layout and delivered with 38.5 h of human cleanup after 27 h of automated layout (baseboard 238 h → 12 h; SOM 190 h → 26.5 h). — [Quilter cleanup](https://www.quilter.ai/blog/cleaning-up-an-ai-designed-computer)
- **DeepPCB vs Quilter [read][V]:** 97.3% vs 87.7% average completion and +44% vias for Quilter on three public boards, with no manual intervention. — [DeepPCB](https://deeppcb.ai/deeppcb-vs-quilter-open-source-routing-compared-2026/)
- **Single-board numbers from §1 [read]:**
  - Fable 5: 65 DRC errors, Freerouting left 49 unrouted, and KiCadRoutingTools routed everything in 1.25 s.
  - tinycomputers: 314/314 nets after the placement change; 121 false-positive DRC flags; about 18 h total.
  - JLCPCB KiCad MCP: 7 issues; 47 → 2 silkscreen warnings.
  - JLCPCB Astra: 46 parity issues; 9 rule categories ignored.
  - JLCPCB EasyEDA Astra: 50 mismatches over 120 pads.
  - JLCPCB Claude EasyEDA: 6 missing GNDs found by read-back.
  - NextPCB: 3 segments per hour GUI-only, versus about 12 min orchestrated.
  - kicad-agentic demo: under 1 s of KiCad time versus 6–7 min of LLM time.
  - Tindie: 9 unrouted nets.
  - StationX HAL: 5 DRC violations on the first gate, then 0.
- **Autocuro, "Can LLMs Verify PCB Designs?" [read][V/A]:**
  - **Setup:** Gemini 3 Pro and ChatGPT 5.1 web UIs on an STM32H7 avionics board (4 layers) and the STM32L496G-DISCO (336 parts, 169-ball BGA, 6 layers).
  - **What worked:** placement review gave "moderate success" with heavily labeled diagrams, as did power/ground commentary when the layers were explicitly labeled.
  - **What failed completely:** routing interpretation; spatial reasoning (distances, overlaps, clearances); trace-width checks; and the dense board, abandoned as "way too much."
  - **MCP attempt:** they tried a KiCad MCP (mixelpixx) and found no mechanical or enclosure context ("must be on edge" versus "nice to have near edge") and weak functional grouping.
  - **Conclusion:** "The extensive data preparation… takes longer than traditional manual review."
  - Source: [Autocuro](https://autocuro.com/blog/can-llms-verify-pcb-designs)
- **JITX, "Testing Generative AI for Circuit Board Design" (June 2024; GPT-4o, Claude 3 Opus, Gemini 1.5) [read][V]:**
  - **Good at:** concept Q&A (Claude 3 Opus gave an "A+" answer on per-layer delay), and datasheet extraction (the 95-row nRF5340 pin table from an 820-page datasheet came out "exactly correct").
  - **Bad at part selection:** "uniformly bad… the 'average' application": it suggested SFP transceivers for a robot joint and missed the needed 3-port switch. "If you're not within 10% or so of the global optimal performance in EE, your suggestions have near-zero value."
  - **Circuits:** a reference-schematic netlist with "invented resistors here and there"; and in an electret pre-amp, the model put a *decoupling* cap where a *coupling* cap was needed, because "LLMs *loved* to give naive advice about decoupling."
  - **Recommended pattern:** "trust a hand-coded BGA footprint generator for the details, and have the LLM tell me which pads to omit," forcing the LLM's pin list and missing-pin list to reconcile in code.
  - Source: [JITX](https://blog.jitx.com/jitx-corporate-blog/testing-generative-ai-for-circuit-board-design)
- **Other benchmarks [snip]:**
  - PCB-Bench (ICLR 2026) covers text, multimodal and full-project PCB comprehension, and finds models "struggle significantly with the spatial logic and strict constraints." — [Lacuna summary](https://lacuna.tiptreesystems.com/work/pcb-bench-benchmarking-llms-for-printed-circuit-board-placement-and-routing/wrk_3aa259abb5e3e453177ad0f77da09471) [read summary]
  - HWE-Bench (spec → board schematic): the top model passes only 8.15%, as cited in a research guide. — [takazudomodular](https://pd.takazudomodular.com/docs/learning/ai-circuit-design-research/) [read guide; paper not read]
  - DRCY, AllSpice's multi-agent pin-by-pin datasheet reviewer, is deployed in production. — [arXiv 2603.15672](https://arxiv.org/pdf/2603.15672) [snip]

### Inferences
- Benchmarks reward getting the netlist and circuit right. Field failures concentrate in footprints, fab rules, cross-tool seams and layout quality. A placer/router project needs its **own layout scorecard benchmark**, run against human reference boards, as the blind-routing test and Speedrun did informally. The scorecard should cover: unrouted count, DRC by severity *including disabled categories*, parity, footprint–datasheet consistency, loop areas, decap distance, ampacity, via count and area.
- Cherry Blossom's 69% → 97% framing ("the gate matters more than the model") and EEBench's harness spread both say the same thing: **harness and tool design is a first-order variable.**

### Gaps
- There is still no independent multi-board benchmark of LLM-driven placement quality.
- Cherry Blossom did not publish a failure taxonomy for its 40 boards.
- The Altium Academy 168-vs-0 comparison is video-only.
- I did not read the PCB-Bench and HWE-Bench papers in full; they are likely covered in `llm_for_eda.md`.

---

## 3. Tool designs that made LLM operation more reliable

### Takeaway
Reliability came from the following:
1. Code/declarative or API representations instead of the GUI.
2. Deterministic engines for geometry, with the LLM orchestrating.
3. A **verdict owned by KiCad (kicad-cli) or the fab**, never by the model.
4. **Independent read-back after every write**, covering the netlist, pin-pad pairs and the live board rather than the saved file.
5. Staged gates in a fixed order: placement check and image, then critical routing, then autoroute, then DRC/parity/DFM.
6. Permission tiers, read-only defaults, Git sandboxes and native undo/commit groups.
7. Candidate/propose-then-apply semantics with monotone acceptance.
8. Grounding references: API references, skills, real part data, and reference designs or validated layout fragments.
9. Locking critical nets and verifying that locked copper survives autorouting.
10. Tools that **refuse** when preconditions can't be verified.

### Cited Findings
- **Code-first, not GUI [read]:**
  - EEBench says code "has worked much better for us than asking a model to draw lines in a GUI". — [EEBench](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)
  - Diode: "Schematics for humans, code for models." — [Diode](https://blog.diode.computer/anthropic-partnership)
  - The tinycomputers generator script and text-format boards are diffable. — [tinycomputers](https://tinycomputers.io/posts/what-routing-314-nets-taught-me-about-ai-assisted-pcb-design.html)
  - JITX: "I'm generating JITX code because it has a text-native representation." — [JITX](https://blog.jitx.com/jitx-corporate-blog/testing-generative-ai-for-circuit-board-design)
  - atopile vendor claim: pin-sharing questions answered 100% correctly via code versus 55% from a PDF. — [atopile](https://atopile.io/enterprise) [snip][V]
- **Deterministic engines [read]:** the NextPCB orchestrated run; KiCadRoutingTools at 1.25 s (Rust A*, about 10× faster than pure Python [snip]); and the JLCPCB and Astra Freerouting flows. — [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test); [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/); [KiCadRoutingTools](https://github.com/atomic14/KiCadRoutingTools) [snip]
- **Verdict ownership [read]:**
  - kicad-agentic-mcp takes its verdict from kicad-cli and errors if checks can't run. — [KiCad forum](https://forum.kicad.info/t/kicad-agentic-mcp-an-ai-assistant-that-edits-your-board-through-kicads-own-api-and-lets-kicad-decide-whether-the-result-is-good/71403)
  - StationX: "trusted because the tools stopped objecting"; "give it zero discretion in verification." — [StationX](https://app.stationx.net/articles/ai-pcb-design)
  - Fab DFM as source of truth. — [tinycomputers](https://tinycomputers.io/posts/what-routing-314-nets-taught-me-about-ai-assisted-pcb-design.html)
- **Read-back verification [read]:**
  - 138/138 pins confirmed by read-back, which found 6 missing GNDs that the API had reported as successful. — [JLCPCB EasyEDA](https://jlcpcb.com/blog/claude-code-pcb-design)
  - A pin-for-pin netlist comparison caught a short that ERC only warned about. — [JLCPCB MCP](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code)
  - An independent 120 pin-pad comparison plus a portability re-check. — [JLCPCB Astra](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad)
  - The scorer was fixed to judge the live board and report its source. — [Konnect PR #648](https://github.com/mixelpixx/Konnect/pull/648) [snip]
- **Surfacing muted checks [read]:**
  - The Adom KiCad Board Audit skill "reads the project's silenced-rule config so a 'clean' pass can't hide muted checks". It walks a checklist of ERC-blind bugs (floating VCAP pins, supply pins tied to GND, wrong-variant VFB dividers, missing pull-ups, crystal load caps), "verifies every suspicion against a primary source," and includes a "verified-correct section so good design doesn't get re-flagged." It was "born from a real audit… where ERC reported 0/0 while the MCU's VCAP pins floated." — [Adom](https://wiki.adom.inc/api/pages/adom/kicad-board-audit/files/README.md)
  - JLCPCB lists its 9 ignored categories explicitly. — [JLCPCB Astra](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad)
- **Staged gates [read]:** tscircuit runs placement, then `check placement`, then a PNG inspection, then routing. — [tscircuit](https://docs.tscircuit.com/guides/circuit-generation/generating-circuit-boards-with-ai). Flux suggests "Placement Check: run Auto-Layout early." — [Flux](https://www.flux.ai/p/blog/ai-auto-layout-just-got-smarter). Run DRC on pre-routes before Freerouting. — [pcbkit #2](https://github.com/bruk-io/pcbkit/issues/2) [snip]
- **Lock and verify critical copper [read]:** "lock that geometry before any autorouter runs… then refill the zones and confirm the locked copper survived". — [JLCPCB Astra KiCad](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad); [JLCPCB EasyEDA Astra](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-easyeda-pro). Flux and Quilter treat existing copper as fixed or "solved." — [Flux](https://www.flux.ai/p/blog/introducing-ai-auto-layout); [Quilter](https://www.quilter.ai/blog/pcb-autorouter-was-the-right-idea)
- **Permission tiers and sandboxing [read]:**
  - The kicad-mcp-pro read-only default with explicit write and manufacturing opt-ins.
  - Review the server code; use stdio only; confine edits to one Git folder.
  - Sources: [JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code); 24 read-only of 377 tools by default per its README [snip] — [kicad-mcp-pro](https://github.com/oaslananka/kicad-mcp-pro)
  - The EasyEDA bridge has no authentication, so add a token and an Origin check. — [JLCPCB](https://jlcpcb.com/blog/claude-code-pcb-design)
  - Diode's reviewer is read-only and "does not edit your files." — [Diode](https://blog.diode.computer/hardware-review)
- **Undo and transactions [snip][G]:** native commit groups give one undo step per agent edit (kicad-mcp-pro #728/#808, Konnect #752). Propose-then-apply candidates with "no apply path" previews: CopperMCP (see §1C). Monotone acceptance, where a change stays only if violation and unconnected counts did not get worse: CopperLoop and kicad-agent-toolkit, as summarized by search; repositories not read.
- **Refusal and honesty in tool semantics [snip][G]:** planners refuse unverifiable outlines (#684); "applicable" only if inside the outline and the score improves (#638); exact references required instead of guessing; tool names corrected to say what they measure (#528).
- **Grounding [read]:**
  - The EasyEDA API reference lets the model "look up real method signatures instead of guessing them." — [JLCPCB](https://jlcpcb.com/blog/claude-code-pcb-design)
  - Cherry Blossom pulls "every footprint from real part data rather than letting a model guess." — [Cherry Blossom](https://www.trycherryblossom.com/blog/gpt-6-astra-pcb-design)
  - Diode's Registry of "validated layout fragment[s]." — [Diode](https://blog.diode.computer/anthropic-partnership)
  - StationX's skills file of learned facts, e.g. TLC555 versus NE555. — [StationX](https://app.stationx.net/articles/ai-pcb-design)
- **Interpretation review before running [read/snip]:**
  - Flux infers net types and the user "can check and change the inference". — [Flux](https://www.flux.ai/p/blog/ai-auto-layout-just-got-smarter)
  - Quilter's compile step has the engineer "review how constraints are interpreted" [snip]. — [Quilter](https://www.quilter.ai/blog/llm-pcb-layout-gpt-6-astra)
  - DeepPCB's warning about "debugging the autorouter's interpretation of your rules." — [DeepPCB](https://deeppcb.ai/the-autorouter-broke-your-trust-heres-whats-actually-different-now/)
- **Convergence and stop rules [read]:**
  - Flux "stops when further search is unlikely to improve quality". — [Flux winter](https://www.flux.ai/p/blog/ai-auto-layout-winter-update)
  - tinycomputers: stop after the second or third failed fix. — [tinycomputers](https://tinycomputers.io/posts/what-routing-314-nets-taught-me-about-ai-assisted-pcb-design.html)
  - A hard $10 spending cap was "all that stood between" an ESP32 firmware agent and a $500 bill. — [StationX](https://app.stationx.net/articles/ai-pcb-design)
- **Tool-surface size:** catalogs run from 105 to 377 tools ([Greg3001](https://github.com/greg3001/kicad-claude-mcp), [ProductOfAmerica](https://github.com/ProductOfAmerica/mcp-server-kicad), [Konnect](https://github.com/mixelpixx/Konnect), [kicad-agentic-mcp: 202](https://forum.kicad.info/t/kicad-agentic-mcp-an-ai-assistant-that-edits-your-board-through-kicads-own-api-and-lets-kicad-decide-whether-the-result-is-good/71403)). A forum regular called them "about 4 million other KiCad MCP things." [snip/read]

### Inferences
- The highest-value tool features are not more operations. They are **trustworthy state and verdicts**:
  - judge the live board;
  - read back after every write;
  - name muted checks;
  - refuse when unverifiable;
  - make each agent step a single undoable commit.
- Latency matters for UX. The KiCad operations are milliseconds; the LLM loop takes minutes. That argues for **coarse operations, such as "place this group under these constraints" or "route these nets", that do a lot per call**, and for running solvers locally rather than having the LLM iterate coordinates.

### Gaps
- There is no A/B study (same model, same board) comparing high-level and low-level tool APIs for PCB work.
- The internals of CopperLoop and kicad-agent-toolkit were seen only through snippets.

---

## 4. Human–AI mixed-initiative design literature: what the HCI/design literature says about effective co-design tools that explain "why"

### Takeaway
Read in full, the classic and recent literature converges on six points.

1. **Automate only where expected value beats inaction, and degrade gracefully under uncertainty.** Horvitz's principle (8): "doing less but doing it correctly."
2. **Keep suggestions beside the designer's work, never overriding it**, and offer **both local refinements and radical alternatives** (Sketchplore; Dream Lens; Sentient Sketchbook; parallel prototyping).
3. **Users' questions about optimizer outputs are overwhelmingly contrastive ("why A rather than B?").** They are best answered by *re-solving under the restriction the question implies* (Krarup et al.; inverse/counterfactual optimization; OptiChat).
4. **Explanations can backfire.** They raise acceptance whether or not the AI is right (Bansal). They reduce overreliance only when they **lower the cost of verifying** the AI (Vasconcelos). Cognitive-forcing designs work but are disliked (Buçinca).
5. **Generative-design users struggle to tell intended features from algorithm glitches, to communicate goals, and to specify everything upfront** (Gmeiner, CHI '23). In one team study, AI help hurt high-performing teams (Zhang/Cagan).
6. **Design rationale capture failed on capture effort and retrieval**, while LLMs can now draft rationale with high recall but low precision. An agent that logs structured rationale at decision time, tied to evidence, removes the main historical barrier.

### Cited Findings

**Mixed-initiative principles (read in full)**
- **Horvitz, "Principles of Mixed-Initiative User Interfaces" (CHI '99) [read][S].** The twelve principles, verified against the paper:
  1. developing significant value-added automation;
  2. considering uncertainty about the user's goals;
  3. considering the user's attention when timing services;
  4. inferring the ideal action in light of costs, benefits and uncertainties;
  5. employing dialog to resolve key uncertainties, "considering the costs of potentially bothering a user needlessly";
  6. allowing efficient direct invocation and termination;
  7. minimizing the cost of poor guesses about action and timing;
  8. **scoping precision of service to match uncertainty: "A preference for 'doing less' but doing it correctly under uncertainty can provide users with a valuable advance towards a solution and minimize the need for costly undoing or backtracking"**;
  9. providing mechanisms for efficient agent–user collaboration to refine results;
  10. employing socially appropriate behaviors;
  11. maintaining working memory of recent interactions;
  12. continuing to learn by observing.

  In LookOut, when it can't find an exact time it "degrades its goal to identifying a span of time" and shows a scoped view the user can directly manipulate. — [Horvitz PDF](https://www.erichorvitz.com/chi99horvitz.pdf)
- **Amershi et al., "Guidelines for Human-AI Interaction" (CHI 2019) [read][S].** 18 guidelines (G1–G18), distilled from 150+ recommendations and tested in a user study with 49 design practitioners. Most relevant here: G2 "Make clear how well the system can do what it can do," G8/G9 efficient dismissal/correction, G10 "Scope services when in doubt," **G11 "Make clear why the system did what it did,"** G15 "Encourage granular feedback," G16 "Convey the consequences of user actions," G17 "Provide global controls." — [Amershi PDF](https://www.microsoft.com/en-us/research/uploads/prod/2019/01/Guidelines-for-Human-AI-Interaction-camera-ready.pdf)

**Interactive optimization, alternatives and co-creativity**
- **Sketchplore (Todi, Weir, Oulasvirta; DIS 2016) [read abstract][S].**
  - Problem: optimizers' "insistence on precise objectives and a point optimum is a poor fit with sketching practices."
  - Approach: a real-time layout optimizer "infers the designer's task to search for both local improvements… and global (radical) alternatives"; suggestions "steer… without overriding the designer or demanding extensive input."
  - [Aalto record](https://research.aalto.fi/en/publications/sketchplore-sketch-and-explore-with-a-layout-optimiser/)
- **Meignan et al., "A review and taxonomy of interactive optimization methods in operations research" (ACM TiiS 2015) [snip][S]:** covers trial-and-error, interactive reoptimization, interactive multiobjective optimization, interactive evolutionary algorithms and human-guided search. It classifies methods by the user's contribution and by system components. — [DOI](https://doi.org/10.1145/2808234)
- **Dream Lens (Matejka et al., Autodesk, CHI 2018) [read][S].**
  - **Two user types:** "engineer" types focus on simulated properties, while "artist" types care about aesthetics, so the tool shows both.
  - **Findings:** "the outlier designs which remained were some of the most interesting for users"; very similar designs should be clustered.
  - **Future-work ideas:** use exploration early to "guide the generation engine," and add "make more like this one."
  - **Scale and quotes:** 16,800 designs were filtered to 1,242 for the studies. P10: "I like that the algorithm does the work, and you can adjust it afterwards."
  - [Dream Lens PDF](https://research.autodesk.com/app/uploads/2023/03/dream-lens-exploration-and.pdf_recFfqgLe5eOFLays.pdf)
- **Parallel prototyping (Dow et al., TOCHI 2010) [snip][S]:** designers who created alternatives in parallel produced ads that outperformed those from serial iteration on click-through and expert ratings. The alternatives were more diverse and self-efficacy rose more. — [Stanford PDF](https://hci.stanford.edu/publications/2010/parallel-prototyping/ParallelPrototyping2010-submitted.pdf)
- **Juxtapose (Hartmann et al., UIST 2008) [snip][S]:** parallel authoring and side-by-side execution let 18 participants survey more options more quickly. — [Stanford](https://hci.stanford.edu/research/juxtapose)
- **Mixed-initiative co-creativity / Sentient Sketchbook (Yannakakis, Liapis, Alexopoulos 2014) [read abstract][S]:** MI-CC means "both the human and the computer proactively making contributions… although the two initiatives do not need to contribute to the same degree." Its suggestions target visual diversity, and the tool was found to "foster human creativity." — [MI-CC PDF](https://www.antoniosliapis.com/papers/mixed_initiative_co-creativity.pdf)

**Explaining optimizer and planner decisions (contrastive and counterfactual)**
- **Krarup et al., "Contrastive Explanations of Plans Through Model Restrictions" (JAIR) [read][S].**
  - **User study:** 168 user questions about plans, about 90% contrastive (17 were non-contrastive or out of scope).
  - **Taxonomy:** FQ1 "Why is A not used…?" (17); FQ2 "Why is A used…?" (75); FQ3 "Why A in state S rather than B?" (35); plus timing variants.
  - **Method:** each question becomes a **constraint added to the model**, the restricted problem is re-solved, and the two plans are compared. This "plan negotiation" covered 89.8% of the questions.
  - [arXiv 2103.15575](https://arxiv.org/pdf/2103.15575)
- **RADAR-X [snip][S]:** a mixed-initiative planning interface that pairs contrastive explanations with revised plan suggestions. It uses the user's preferred plan as the "foil." — [arXiv 2011.09644](https://arxiv.org/pdf/2011.09644)
- **Korikov & Beck, "Counterfactual Explanations via Inverse Constraint Programming" (CP 2021) [read abstract][S]:** a counterfactual explanation is "the minimal change to the world required for a user's desired decisions to be made." Inverse optimization finds it for a user query that fixes some variables; the paper evaluates it on knapsack and scheduling problems. — [CP 2021 PDF](https://tidel.mie.utoronto.ca/pubs/Counterfactual_CP2021.pdf)
- **OptiChat (Chen, …, Li; INFORMS J. Data Science 2025) [read abstract][S]:** an LLM dialogue system that helps practitioners "interpret model formulation, diagnose infeasibility, analyze sensitivity… evaluate modifications, and provide counterfactual explanations." It uses **function calls and code generation against the solver to "minimize the risk of hallucinations."** — [arXiv 2501.08406](https://arxiv.org/pdf/2501.08406)
- **XAI-for-OR references (citation level) [snip]:** De Bock et al., EJOR 2024; Erwig & Kumar 2024; Aigner et al., AAAI 2024; Goerigk & Hartisch 2023; Forel et al., ICML 2023. — [arXiv 2412.01264](https://arxiv.org/pdf/2412.01264)

**Trust calibration and the explanation paradox (read in full)**
- **Bansal et al. (CHI 2021) [read][S]:**
  - **Main finding:** "explanations increased the chance that humans will accept the AI's recommendation, regardless of its correctness."
  - **Adaptive explanation:** they tested a design that explains the top-two alternatives only when model confidence is low, "inspired by an efficient assistant that divulges more information (confessing doubts and arguing for alternatives) only when it is unsure."
  - [arXiv 2006.14779](https://arxiv.org/pdf/2006.14779)
- **Vasconcelos et al., "Explanations Can Reduce Overreliance on AI Systems During Decision-Making" (CSCW 2023, 5 studies, N=731) [read abstract][S]:**
  - People strategically weigh the cost of verifying against the cost of relying on the AI.
  - Overreliance fell when explanations made verification easier, and was also affected by task difficulty and incentives.
  - Earlier null results may be "due in part to the explanation not sufficiently reducing the costs of verifying the AI's prediction."
  - [arXiv 2212.06823](https://arxiv.org/pdf/2212.06823)
- **Buçinca, Malaya, Gajos, "To Trust or to Think" (CSCW 2021, N=199) [read abstract][S]:** three cognitive-forcing designs significantly reduced overreliance compared with simple XAI: *on demand* (click to see the AI's suggestion), *update* (decide first, then see the AI) and *wait*. But "people assigned the least favorable subjective ratings to the designs that reduced the overreliance the most," and the benefit was larger for people high in Need for Cognition. — [Gajos lab PDF](https://kgajos.seas.harvard.edu/papers/bucinca21trust.pdf)
- **Zhang, Raina, Cagan, McComb, "A cautionary tale about the impact of AI on human design teams" (Design Studies 2021) [read abstract][S]:** the AI "boosts the initial performance of low-performing teams… but always hurts the performance of high-performing teams." — [Penn State record](https://pure.psu.edu/en/publications/a-cautionary-tale-about-the-impact-of-ai-on-human-design-teams/)
- **Engineers' trust (2026 survey, general engineering) [snip][V]:** 86% use AI, but only 6% trust its output without hesitation. — [Allwork.space](https://allwork.space/2026/02/86-of-u-s-engineers-use-ai-but-only-6-fully-trust-it-2026-survey-finds/)

**Generative design and CAD co-creation**
- **Gmeiner et al., "Exploring Challenges and Opportunities to Support Designers in Learning to Co-create with AI-based Manufacturing Design Tools" (CHI 2023) [read][S].** 14 designers used Fusion 360 Generative Design or SimuLearn in think-aloud studies, followed by a peer-guide study.
  - **Understanding outputs:** designers had "difficulty understanding the cause and remedy of 'weird' outcomes… were unable to determine whether such design features were intended or caused by algorithmic glitches."
  - **Communicating goals:** they "felt unable to communicate their design goals."
  - **Upfront specification:** they found it hard to "specify all required parameters upfront instead of modeling and testing a part step-by-step."
  - **What they wanted:** "a more conversational form of interaction," contextual awareness and project-relevant examples. One likened the tool to "working with a skilled teammate who is not listening to you."
  - **What worked:** the successful designers "systematically test[ed] the boundaries of its capabilities early on" and self-explained the AI's behavior. Effective human guides prompted reflection and **suggested "alternative design goals that align with the AI's capabilities."**
  - [arXiv 2303.00192](https://arxiv.org/pdf/2303.00192)
- **Generative design role study (Saadi & Yang, ASME JMD 2023) [snip][S]:** a grounded-theory interview study of six experienced designers. — [ASME](https://asmedigitalcollection.asme.org/mechanicaldesign/article/145/4/041411/1156493/Generative-Design-Reframing-the-Role-of-the)
- **Text-to-CAD clarification: ProCAD, "Clarify Before You Draw" (ICML 2026) [read abstract][S].** Fine-tuned models "hallucinate dimensions when the text is ambiguous." ProCAD's clarifying agent "asks targeted clarification questions only when necessary." It reduced the invalidity ratio from 4.8% to 0.9% and Chamfer distance by 79.9% compared with frontier models, including Claude Sonnet 4.5. — [arXiv 2602.03045](https://arxiv.org/abs/2602.03045)
- **Other CAD-agent evidence [snip][S]:**
  - Visual feedback was the best of four text-to-CAD agent workflows. — [Design Society](https://www.cambridge.org/core/journals/proceedings-of-the-design-society/article/from-text-to-design-a-framework-to-leverage-llm-agents-for-automated-cad-generation/5BD8D63CFCED28BDD7A01313162FFBE7)
  - Spatial and topological requirements are the hardest to satisfy. — [CADTests](https://arxiv.org/pdf/2605.07807)
  - CADialogue reports 95.71% task success with human-in-the-loop refinement. — [CAD journal](https://www.sciencedirect.com/science/article/abs/pii/S0010448525001678)

**Design rationale**
- **Karsenty (CHI '96) [snip][S]:** captured rationale answered only 41% of six professional designers' questions about a past design (paywalled; snippet). — [ACM DL](https://dl.acm.org/doi/fullHtml/10.1145/238386.238462)
- **IBIS and QOC barriers [snip][S]:** capture overhead and interruption of flow; early IBIS successes didn't scale; retrieval from large, decontextualized argument records is hard. — [Buckingham Shum](https://www.semanticscholar.org/paper/QOC-Design-Rationale-Retrieval:-A-Cognitive-Task-Shum/65037a32d6bb6d068f773edab54adf6d567d2dca); [gIBIS/QOC 15 years on](https://www.researchgate.net/publication/42790084_Hypermedia_support_for_argumentation-based_rationale_15_years_on_from_gIBIS_and_QOC)
- **LLM-generated design rationale (Zhao et al.?, ACM TOSEM 2025) [read abstract][S]:**
  - **Setup:** 100 architecture problems, five LLMs, and zero-shot, CoT and agent prompting, scored against expert rationale.
  - **Scores:** **precision 0.267–0.278, recall 0.627–0.715.**
  - **Arguments not mentioned by the experts:** "64.45% to 69.42%… are also helpful," while "1.59% to 3.24%… are potentially misleading."
  - [arXiv 2504.20781](https://arxiv.org/abs/2504.20781)
- **ADR generation [snip][S]:** naming "Architectural Decision Record" in the prompt improved zero-shot output, though results stay below human level. — [arXiv 2403.01709](https://arxiv.org/pdf/2403.01709)
- **PCB-specific rationale need [read]:**
  - Diode: review is "reconstructing the intent of the engineer," and "intent lives outside the file." — [Diode](https://blog.diode.computer/hardware-review)
  - JLCPCB on reuse: a forum commenter notes you must work out "which layout decisions mattered" when reusing reference circuits [snip]. — [atopile search context](https://forum.kicad.info/t/open-ai-claims-gpt-6-astra-can-make-pcb-boards/71487)
  - DeepPCB on RL: "can't articulate the underlying principle." — [DeepPCB](https://deeppcb.ai/the-autorouter-broke-your-trust-heres-whats-actually-different-now/)

### Inferences
- **"Why here and not there?" should be implemented as Krarup-style plan negotiation.** Take a user question about a part or net, compile it into a constraint (pin C12 at the alternative location, or forbid layer 2 for net X), re-run the deterministic placer or router, and present a **measured delta**: loop area, wirelength, vias, DRC, congestion. An LLM (OptiChat-style) translates the question into a constraint and the delta into prose. It never invents the numbers.
- **Explanations must lower verification cost (Vasconcelos), not just justify (Bansal).** Each explanation should come with a one-click check or highlight: the measured loop polygon, the rule ID and its location, the datasheet page and table row. When confidence is low, show the top-two alternatives, as in Bansal's adaptive explanation.
- **Show both views (Dream Lens):** metrics for "engineers" and rendered aesthetics for "artists." Quilter's observation that output gets "rejected on sight" when it looks wrong confirms that aesthetics count for acceptance.
- **The agent should state its interpretation of goals before solving, and ask only when necessary.** This follows Horvitz #5, ProCAD, Flux's editable net-type inference, Quilter's constraint-interpretation review, and Gmeiner's "communicating goals" finding.
- **Cagan's result is an argument for adjustable autonomy.** Experts need a "suggest only / don't touch" mode and global controls (Amershi G17). Novices need guardrails that prevent automation bias.
- **Structured rationale should be logged automatically at action time.** Records should be in IBIS/QOC style (issue, options, criteria, decision, evidence), anchored to board objects, which solves both the capture-overhead and the retrieval problems. Because LLM rationale has low precision, every claim must carry a provenance tag: measured, rule, datasheet, or inference. This follows StationX's "label inferences as inferences."

### Gaps
- I found no peer-reviewed HCI study of PCB designers using an AI placement or routing co-pilot, and no published XAI work on PCB or IC placement decisions.
- I found no user study of Zoo, Onshape AI or Fusion text-prompt generative design with practicing engineers.
- Karsenty and the Dow parallel-prototyping paper were not read in full (paywall and broken mirror).

---

## 5. How expert PCB designers want AI help: surveys, polls, and top concerns

### Takeaway
Use of *some* AI is near-universal in the one large 2026 PCB survey (Weidmuller/EETech: 91%, a vendor-sponsored study of 400 North American engineers). Designers mostly want an **acceleration layer inside existing workflows**, and their top wish-list item is **real-time error detection**. Their concerns:
- trust and auditability, rooted in decades of bad autorouters;
- the opacity of RL engines;
- quality on high-speed, RF and HDI work;
- IP security;
- aesthetics and house style ("artwork");
- the time cost of explaining a task versus just doing it.

Independent, academic surveys of PCB designers on AI remain absent.

### Cited Findings
- **Weidmuller USA / EETech 2026 survey (400 NA engineers) [read][V]:** "91% have used AI-based tools in their PCB design workflow, with faster design iterations being seen currently as the primary value." 75% view AI "as a productivity and acceleration layer within existing workflows." Under "wish existed," respondents cited the "lack of real-time error detection and fully autonomous text to the PCB." Almost 80% value reliability most in component selection. — [Automation World](https://www.automationworld.com/analytics/news/55393457/weidmuller-pcb-design-survey-reveals-ai-tool-impacts)
- **General engineers [snip]:** 86% use AI, 6% trust its output without hesitation, and about 90% verify. — [Allwork.space](https://allwork.space/2026/02/86-of-u-s-engineers-use-ai-but-only-6-fully-trust-it-2026-survey-finds/)
- **Unverified IPC claim [snip]:** a 30% reduction in design-to-tapeout time, attributed to IPC. — [AtlasPCB](https://www.atlaspcb.com/news/news-ai-pcb-design-tools-cadence-altium-ml-2026/)
- **Autorouter distrust [read][V]:**
  - Engineers "learned not to trust them"; Chris Gammell's "Never trust the autorouter" shirt. — [Quilter](https://www.quilter.ai/blog/pcb-autorouter-was-the-right-idea)
  - "~90% completion with the autorouter, then spending 'several weeks tearing up and rerouting tracks to get to 100%'" (an Eng-Tips anecdote cited by DeepPCB). — [DeepPCB](https://deeppcb.ai/the-autorouter-broke-your-trust-heres-whats-actually-different-now/)
  - Configuration overhead is a dealbreaker: "By the time you've configured everything, you might have already routed the board manually". — [Flux](https://www.flux.ai/p/blog/introducing-ai-auto-layout)
- **Explaining versus doing [read][C]:** "I would have done a better layout for these three components faster than typing that prompt." — [KiCad forum](https://forum.kicad.info/t/kicad-agentic-mcp-an-ai-assistant-that-edits-your-board-through-kicads-own-api-and-lets-kicad-decide-whether-the-result-is-good/71403). Autocuro found data preparation took longer than manual review. — [Autocuro](https://autocuro.com/blog/can-llms-verify-pcb-designs)
- **Aesthetics and house style [read][V]:** "What 'looks right' varies by company, by team, sometimes by individual reviewer." Cleanup aligned output with the team's "comfort margins and power-integrity preferences." — [Quilter autorouter](https://www.quilter.ai/blog/pcb-autorouter-was-the-right-idea); [Quilter cleanup](https://www.quilter.ai/blog/cleaning-up-an-ai-designed-computer)
- **Where designers draw the line [read/snip]:**
  - High-speed, RF, HDI/BGA and novel analog work stay with humans. — [KiCad forum](https://forum.kicad.info/t/open-ai-claims-gpt-6-astra-can-make-pcb-boards/71487) [snip]; [Flux winter](https://www.flux.ai/p/blog/ai-auto-layout-winter-update) [read]
  - Quilter's operating range excludes BGA fanout, length matching and RF as mature features. — [Quilter](https://www.quilter.ai/blog/pcb-autorouter-was-the-right-idea) [read]
- **Skill-atrophy concern [read][V]:** "Delegating layout to AI while atrophying your own layout skills is a trap." — [DeepPCB](https://deeppcb.ai/the-autorouter-broke-your-trust-heres-whats-actually-different-now/). A hobbyist "was not feeling much of an accomplishment." — [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/)
- **IP concerns [read/snip]:** Quilter offers deployment inside the customer's own AWS, Azure or GCP for ITAR and IP-sensitive work [read]. PCD&F flags IP security as a concern [snip]. — [Quilter](https://www.quilter.ai/blog/pcb-autorouter-was-the-right-idea); [PCD&F](https://pcdandf.com/pcdesign/index.php/current-issue/289-best-practices/18594-ai-in-pcb-design-it-s-already-here)

### Inferences
- The demand signal points to a co-pilot that:
  - **catches errors in real time**;
  - is **auditable step by step**;
  - **learns house style from the user's cleanup edits**;
  - lets experts lock what they care about.

  A one-shot "autoroute everything" button is the wrong primary interface.
- "Faster than typing the prompt" is a real cost. On small edits, direct manipulation should stay primary, with the AI offering suggestions alongside it (Horvitz's coupling of automation with direct manipulation).

### Gaps
- I found no primary Altium, Cadence, Siemens, Zuken or IPC survey on AI in PCB layout.
- I found no academic interview study of PCB layout professionals about AI.
- The Weidmuller trust and concern items beyond the press release were not available.

---

## 6. Implications for an LLM-driven KiCad placer/router

### Takeaway
Build a **mixed-initiative orchestrator**:
- **The LLM** handles intent capture, constraint authoring, sequencing, failure triage, "noticing," and explanation.
- **Deterministic, KiCad-native engines** own geometry, routing, state and verdicts.
- **The human-facing layer** shows the agent's interpretation before it acts, presents a few distinct alternatives with scorecards, gives every step as an undoable diff, and answers "why here, not there?" by re-solving under the implied constraint. Every claim carries a tag saying how it was established.

### Cited Findings (evidence base for the recommendations; all detailed above)
- **LLM-pushed geometry fails or crawls:** [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test), [StationX](https://app.stationx.net/articles/ai-pcb-design), [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/), [Copperhead #398](https://github.com/copperheadhq/copperhead/pull/398)
- **"Success" responses that weren't, and stale state:** [JLCPCB EasyEDA](https://jlcpcb.com/blog/claude-code-pcb-design), [Konnect #595](https://github.com/mixelpixx/Konnect/issues/595), [KiCAD-MCP-Server PR #422](https://github.com/mixelpixx/KiCAD-MCP-Server/pull/422), [JLCPCB MCP (batch ran twice)](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code)
- **Invisible failures:** [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/), [JLCPCB EasyEDA Astra](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-easyeda-pro), [Adom](https://wiki.adom.inc/api/pages/adom/kicad-board-audit/files/README.md), [Cherry Blossom](https://www.trycherryblossom.com/blog/gpt-6-astra-pcb-design)
- **Loops and when to stop:** [tinycomputers](https://tinycomputers.io/posts/what-routing-314-nets-taught-me-about-ai-assisted-pcb-design.html), [blwfish PR #158](https://github.com/blwfish/kicad-mcp/pull/158), [Flux winter](https://www.flux.ai/p/blog/ai-auto-layout-winter-update)
- **Noticing congestion helps:** [tinycomputers](https://tinycomputers.io/posts/what-routing-314-nets-taught-me-about-ai-assisted-pcb-design.html)
- **Latency and nondeterminism:** [KiCad Agentic MCP](https://forum.kicad.info/t/kicad-agentic-mcp-an-ai-assistant-that-edits-your-board-through-kicads-own-api-and-lets-kicad-decide-whether-the-result-is-good/71403), [DEV](https://dev.to/dibyaprakash_pradhan/kicad-and-ai-in-2026-mcp-servers-scripts-and-what-actually-works-3p1a)
- **HCI evidence:** [Horvitz](https://www.erichorvitz.com/chi99horvitz.pdf), [Amershi](https://www.microsoft.com/en-us/research/uploads/prod/2019/01/Guidelines-for-Human-AI-Interaction-camera-ready.pdf), [Krarup](https://arxiv.org/pdf/2103.15575), [OptiChat](https://arxiv.org/pdf/2501.08406), [Bansal](https://arxiv.org/pdf/2006.14779), [Vasconcelos](https://arxiv.org/pdf/2212.06823), [Buçinca](https://kgajos.seas.harvard.edu/papers/bucinca21trust.pdf), [Gmeiner](https://arxiv.org/pdf/2303.00192), [Dream Lens](https://research.autodesk.com/app/uploads/2023/03/dream-lens-exploration-and.pdf_recFfqgLe5eOFLays.pdf), [Sketchplore](https://research.aalto.fi/en/publications/sketchplore-sketch-and-explore-with-a-layout-optimiser/), [Zhang/Cagan](https://pure.psu.edu/en/publications/a-cautionary-tale-about-the-impact-of-ai-on-human-design-teams/), [DR-LLM](https://arxiv.org/abs/2504.20781)

### Inferences (concrete design principles; these are my synthesis, not sourced claims)

**A. Tool API (what the LLM can call)**
1. **No coordinate math in the model.** Offer relational, intent-level placement operations, for example:
   - `place_near(ref, anchor_pin, max_mm, side)`
   - `keep_together(group)`
   - `align/distribute`
   - `orient_pin_toward`
   - `place_in_region`
   - `fix(ref)`
   - text/label placement in board coordinates

   All transforms go through KiCad's own code (IPC API or pcbnew), in **one shared orientation helper**, and must preserve 3D models, zones and text.
2. **The LLM writes constraints; solvers compute geometry.** A deterministic placer (sequential packing or force-directed, followed by legalization) and a router (KiCadRoutingTools, Freerouting, or internal) do the work. The LLM edits the *constraint set* between runs, "hardening" intent in Seve's sense, rather than moving parts one at a time.
3. **Ground truth comes only from KiCad (kicad-cli or IPC) and the fab profile.**
   - Never re-implement approximations such as AABB courtyards.
   - **Always judge the live board, and report which source was judged.**
   - Set fab-specific DRC rules as a precondition.
   - Every "clean" report lists **disabled or ignored categories**.
4. **Read back after every write.** Each mutating call returns a structured *observed* diff of what actually changed in KiCad: parts moved, pads and nets changed, attributes, 3D models. A mismatch with what was intended becomes an error. Netlist parity and pin-by-pin pad↔net comparison are first-class tools.
5. **Semantic checkers beyond DRC/ERC:**
   - footprint versus MPN/datasheet (pad count, pitch, body width, package variant);
   - **library-identity uniqueness**, to catch same-name aliasing;
   - ratings versus net voltage and current;
   - ERC-blind checklists: floating mandatory pins, supply pins on GND, divider VFB variant, pull-ups, crystal load capacitance;
   - layout quality: decap-to-pin distance, switching-loop area, power-trace ampacity, return-path continuity, diff-pair skew, congestion map.
6. **Refuse instead of guess.** If an outline, rule set, part reference or check result can't be verified, return a typed refusal. Plans are "applicable" only if every target is legal *and* the scorecard improves. If DRC can't run, say so; never report "clean."
7. **Transactions:**
   - each agent step is a single native commit (one Ctrl+Z);
   - proposals are **immutable candidates** with preview and no apply path until the user accepts;
   - every committed step is auto-snapshotted to Git;
   - `compare(a, b)` is available.
8. **Coarse, high-yield calls** cut multi-minute LLM loops when KiCad operations take milliseconds. Examples: "place this functional block under these constraints"; "route these nets with these rules and protect locked copper"; "verify locked copper survived plus zone refill."
9. **Perception sized for LLMs:**
   - compact JSON summaries (per-net status, per-region congestion, top-N violations with object IDs and coordinates);
   - truncation metadata (`_total`, `_truncated`);
   - labeled renders (refdes, highlighted nets, violation markers, region crops) only as a secondary channel.
10. **Failure attribution for "noticing."** When a solver stalls, return *where* and *why*: "49 unrouted, 80% terminating in region R near U6–U10; channel capacity X versus demand Y." The LLM is good at turning that into a placement-change hypothesis.

**B. Agent loop**
1. **Interpret → confirm → constrain → place (solver) → placement gate (check + render) → route critical → lock → autoroute rest → refill + locked-copper check → DRC/parity/semantic/DFM gate → triage → repeat.**
2. **Monotone acceptance:** keep a change only if violations and unconnected items don't get worse. Keep a regression ledger.
3. **Loop budget and escalation:** cap retries per issue (2–3), total iterations and spend. When stalled, stop and present the evidence and options to the human, rather than "happily trying to fix it."
4. **Recognize every failure category**, including "unconnected," "silkscreen" and "parity," so autofix loops can't stall silently.
5. **Separate builder and reviewer.** The reviewer is read-only, evidence-only ("no evidence, no report"), severity-ranked, and keeps a verified-correct list.
6. **Reference designs and validated fragments first.** Use datasheet layouts and Registry-style fragments as constraints before free placement.
7. **Clarify only when needed (ProCAD, Horvitz #5):** connector edges, mechanical keep-outs, sensitive nets, fab and stackup, before long solver runs.
8. **Determinism and provenance:** record seeds, solver versions, constraint sets and prompts, so a run can be reproduced. Accept that LLM choices vary, but make the *solver* step deterministic given constraints.
9. **A skills/lessons file** keeps learned facts across sessions (part quirks, fab rules, house style), each tagged with its source.

**C. Human-facing UX and explanation of choices**
1. **Show the interpretation before acting.** List the inferred net classes and priorities, critical loops, keep-outs and fab rules, all editable, as Flux and Quilter do. This addresses the Gmeiner "communicating goals" problem.
2. **Suggestions beside the canvas; direct manipulation stays primary (Sketchplore).** Provide one-click accept, reject or tweak, **lock** controls, and a global autonomy dial running from suggest-only through "do region" to "do board" (Amershi G17; Cagan cautionary tale).
3. **Two to four distinct alternatives**, not one answer: for example compact, connector-left or thermal-spread. Each comes with a **scorecard plus rendered view** (metrics for "engineers," visuals for "artists"), an outlier option, and **"more like this"** (Dream Lens; parallel prototyping).
4. **Contrastive "why here, not there?" by re-solving (Krarup, Korikov, OptiChat).** Clicking an object or dragging a ghost alternative compiles the question into a constraint, re-runs the solver, and shows the measured delta. The LLM narrates but never fabricates numbers.
5. **Explanations that lower verification cost (Vasconcelos).** Every claim links to a one-click check: highlight the loop polygon, jump to the DRC marker, open the datasheet page. Each claim is tagged **measured / rule / datasheet / estimate / inference** (StationX; kicad-mcp-pro "closed-form estimates"). When confidence is low, show the runner-up and why (Bansal's adaptive explanation).
6. **Object-anchored rationale log (IBIS/QOC-lite).** Each decision record holds the issue, options considered, criteria, choice and evidence, and is attached to the parts, nets or zones it affected. It is searchable, survives edits, and is exportable as a design-review document. This removes capture overhead and contextualizes retrieval.
7. **Calibrated sign-off.** For release gates, consider a light **cognitive-forcing** step: the reviewer marks the top risks *before* seeing the AI's verdict (Buçinca's "update" design). Use it sparingly, because users dislike it. Never show a single green "looks good" to novices; show the residual-risk list and what was not checked.
8. **Diff-first review and house-style learning.** Every step is a visual and textual diff that can be reverted individually. Treat the user's cleanup edits (bigger pours, straighter routes, label moves) as preference signals for future runs (Quilter's cleanup categories).
9. **Respect the "faster than typing" threshold.** For tiny edits, offer inline suggestions or completions rather than a chat round-trip. Save the agent loop for block- and board-level work.

### Gaps
- None of these principles has been A/B tested on PCB tasks in the literature I found.
- No study measured whether alternatives, contrastive re-solve explanations or object-anchored rationale improve PCB designers' outcomes or trust calibration. That would be a valuable evaluation for this project, for example using EEBench-style deterministic grading extended to layout plus a small designer study.
