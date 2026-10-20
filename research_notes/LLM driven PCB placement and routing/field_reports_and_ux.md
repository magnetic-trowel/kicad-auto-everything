# Field Reports of LLM/Agent-Driven PCB & EDA Work, and Human–AI Co-Design / Design-Rationale UX

> **Method and reliability note (read first).** In this session, WebFetch could not resolve any external host (DNS failure in the sandbox), and the GitHub API was not enabled. The shared WebSearch budget ran out after about 37 queries. Every finding below therefore comes from search-engine summaries and snippets of the cited pages, not from full-page reads. Specific numbers (DRC counts, scores, yields) are reported as those summaries gave them, so the report writer should spot-check headline numbers against the originals where possible.
>
> **Evidence labels:**
> - **[A]** a single-person anecdote or field report.
> - **[C]** community discussion (HN, forums, Lobsters).
> - **[V]** vendor or self-reported claims, possibly with a conflict of interest.
> - **[G]** GitHub issues or PRs, meaning concrete bug reports from tool builders.
> - **[S]** systematic or peer-reviewed work.
>
> This file is meant to complement `llm_for_eda.md`, which covers the algorithm and paper literature. Where the two overlap (GPT-6 Astra, EEBench), this file adds only practitioner-level detail.

---

## 1. Field reports: what actually happens when an LLM/agent drives KiCad or other EDA tools (what worked, what broke, workarounds)

### Takeaway
By late 2026, many people have used Claude, GPT, or other agents to produce real, fabricated boards that worked on first power-up. Every such report shares three traits. The board is simple, mostly digital, and 2–4 layers. Bulk routing is done by a deterministic router (Freerouting, KiCadRoutingTools, or a vendor engine), not by the LLM. A DRC/ERC/parity loop feeds errors back to the model. The failures repeat across reports: wrong or invented footprints, missing connections, rotation and coordinate math errors, ignoring or not configuring fab rules, poor placement quality (thin power traces, sloppy loops), routing stalls, and very slow GUI-level operation. The fixes are also consistent: work code-first or through an API rather than the GUI, use deterministic solvers for geometry, run verification gates at every stage, keep work in Git, and keep a human reviewer.

### Cited Findings

**End-to-end case studies (fabricated or near-fabricated boards)**

- **A6M-Zero "This PCB is brought to you by Fable 5" (Sept 2026) [A].**
  - Prompt and rules: a short plain-English prompt asked for an RP2350 dev board driving an E-ink display. The author set two rules: no manual edits, and every pre-manufacturing problem goes back to the model. — [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/)
  - Initial output: a KiCad project with 65 footprints, 54 nets, and 118 unconnected lines. The first pass had **65 DRC errors**, which were "only mentioned to Fable", with no other intervention. — [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/); [Adafruit](https://blog.adafruit.com/2026/09/15/this-pcb-is-brought-to-you-by-fable-5-a6m-zero)
  - **Footprint errors:** two footprints were wrong. A W25Q128JVS SPI flash in **SOIC-8 wide was sitting on SOP-8 pads**, and the transistor for the E-ink boost converter was undersized. The flash was swapped for a P25Q64SH. — [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/)
  - **Routing:** Freerouting ran about 2 minutes and 17 passes, then plateaued with **49 connections still unrouted**. Claude hand-routed the rest. Later, the author tried **KiCadRoutingTools, which routed all connections in 1.25 s**. — [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/); [Adafruit](https://blog.adafruit.com/2026/09/15/this-pcb-is-brought-to-you-by-fable-5-a6m-zero)
  - **Outcome:** a 4-layer, 31.8 × 37.32 mm board. Five assembled boards from JLCPCB cost about €130. The board enumerated over USB on first plug-in, with no 3V3–GND short. — [Adafruit](https://blog.adafruit.com/2026/09/15/this-pcb-is-brought-to-you-by-fable-5-a6m-zero); [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/)
  - **Community critique [C]:**
    - Lobsters commenters noted it is "simple digital routing". They asked whether the DRC rules were ever set to JLCPCB's capabilities (KiCad's defaults are conservative), and pointed out that Raspberry Pi publishes reference designs for this chip that could have guided layout. — [Lobsters](https://lobste.rs/s/yedfbj/this_pcb_is_brought_you_by_fable_5)
    - An HN commenter who reviewed the board was skeptical of its routing and placement. Another listed typical AI mistakes: **improperly rotated connectors** and **endless routing loops on complex boards**. That commenter argued that better DRC feedback would let the AI self-correct. — [HN](https://news.ycombinator.com/item?id=49695689)
- **Related hand-routing hazard [G]:** in pcbkit, if hand-laid (or agent-laid) copper clashes with itself or a pad, Freerouting cannot resolve it and every attempt runs to the **900 s hard timeout**. The proposed fix is to run DRC on pre-routes before starting Freerouting. — [pcbkit issue #2](https://github.com/bruk-io/pcbkit/issues/2)
- **atomic14 (Chris Greening) "Vibe-coding a PCB – surprisingly good" (July 2025) [A].**
  - Setup: an ESP32-S3 dev board, specified in atopile, which is code that compiles to a KiCad PCB. Claude Code did better than Cursor on this task. The spec required LCSC part numbers and 0603 passives. — [atomic14 Substack](https://atomic14.substack.com/p/vibe-coding-a-pcb-surprisingly-good); [atomic14 blog](https://www.atomic14.com/2025/07/12/vibing-hardware)
  - **Failure:** the first build "succeeded" but **left components unwired**. After a nudge, everything was wired, but the RC circuit on EN was **missing its capacitor**. The author also swapped a 330 Ω the AI picked for 10 kΩ. Verdict: AI is "your enthusiastic, if forgetful, assistant." — [atomic14 Substack](https://atomic14.substack.com/p/vibe-coding-a-pcb-surprisingly-good)
  - **HN critique [C]:** the LLM really produced only the BOM and netlist, while placement and routing were done in KiCad (by hand or autorouter). Commenters criticized a **minimum-width trace carrying power** across the board to the ESP32, and tight clearances. One amateur said they send schematic screenshots to an LLM, which caught a mis-wired MOSFET, and that "it's very reassuring to get green light from LLM". That comment is an automation-bias signal. — [HN "Vibe-Coding a PCB"](https://news.ycombinator.com/item?id=44542880)
- **JLCPCB "KiCad MCP: Design a PCB with Claude Code in KiCad 10" (Oct 14, 2026) [V/A].**
  - Result: Claude turned a 5 A XL4015 buck-converter netlist into a 2-layer, 63 × 33 mm layout with **zero ERC/DRC errors "after minor initial fixes"**. — [JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code)
  - Real problems found: an **incorrect ground connection on the XL4015 VC pin**, and a **78L05 that could not handle the 36 V maximum input**. **KiCad's ERC did not catch a connection error between the current-sense and current-limit set-point nets**; a pin-by-pin netlist comparison did. The board had not been fabricated or bench-tested. — [JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code)
  - Workaround advice: start the MCP server **read-only**, and allow edits only in a **dedicated, Git-tracked folder**. — [JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code)
  - A kicad-mcp-pro issue tracks reproducing this JLCPCB workflow end to end to "verify reported failures". — [kicad-mcp-pro #1314](https://github.com/oaslananka/kicad-mcp-pro/issues/1314)
- **JLCPCB "Can GPT-6 Astra design a PCB in KiCad?" [V/A].** A four-line brief became a 2-layer, two-sheet project on a 44 × 34 mm board, rebuilt from a datasheet reference circuit. KiCad reported **46 schematic-parity issues**, which were fixed in the source data. JLCPCB calls it a milestone, "not manufacturing approval". — [JLCPCB KiCad review](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad)
- **JLCPCB GPT-6 Astra in EasyEDA Pro [V/A].** Initial verification reported **50 association mismatches involving 120 pads**. The cause was a tool-side import bug: EasyEDA Pro treated distinct footprints that shared a library name as the same footprint. — [JLCPCB EasyEDA review](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-easyeda-pro)
- **NextPCB GPT-6 Astra routing test (Hubert Hu) [A].**
  - Unrestricted run: the model did not do the routing math. Its workflow was **KiCad DSN export → Freerouting → SES import**, so the LLM orchestrated and Freerouting computed. The run took about 12 minutes.
  - **GUI-only variant:** after an hour, the model had completed only **three short trace segments**. The author notes that two runs are not a benchmark. — [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test)
- **Community blind-routing test of GPT-6 Astra (GitHub) [A].** On a medium board with 63 footprints and 247 pads, unconnected items went from 125 to 0, with DRC/ERC at 0 errors and 0 warnings "within the checks actually enabled". The result was **larger and less tidy than KiCad's reference board**, and the author says it is not a controlled benchmark. — [cyjjjj-21/gpt6-astra-kicad-blind-routing](https://github.com/cyjjjj-21/gpt6-astra-kicad-blind-routing/blob/main/README.md)
- **tinycomputers.io "Redesigning a PCB with Claude Code and Open-Source EDA Tools" (Mar 2026 series) [A].**
  - Toolchain: Claude Code with gEDA/pcb-rnd and Freerouting, producing Gerbers from the terminal.
  - The author argues that pcb-rnd's text format is easier for AI and scripts, and that "you can diff two boards and see exactly what changed."
  - Later posts move to a **Python generator script that emits the board file directly, with no schematic and no GUI**. Claude audited the generator, including pin mapping against the TI datasheet.
  - The v0.4 respin post includes **"six hours of Freerouting clearance debugging"** and the limits of LLM-assisted hardware design. — [tinycomputers Part 1](https://tinycomputers.io/posts/redesigning-a-pcb-with-claude-code-and-open-source-eda-part-1.html)
  - A follow-up post, "What Routing 314 Nets Taught Me About AI-Assisted PCB Design", exists, but its content was not retrievable. — [tinycomputers](https://tinycomputers.io/posts/what-routing-314-nets-taught-me-about-ai-assisted-pcb-design.html)
- **Tindie blog (gongyu, Sept 8, 2026) [A].** The project was an ESP32-S31 robot-head controller with camera, mics, speaker, LCD, 12 RGB LEDs, IMU, and ToF sensor. Inputs were **two Espressif reference-board PDFs plus a concept image**. The author started with GPT-5.6 in chat and normally uses Claude Code for software, with GPT for architecture review. The final verdict was not retrievable. — [Tindie](https://blog.tindie.com/2026/09/i-designed-a-kicad-pcb-with-gpt-5-6-and-gpt-6-and-it-changed-how-i-think-about-hardware-design/)

**Practitioner sentiment (forums, HN)**

- **EEVblog "Claude Code for pcb design?" [C].** The thread spans 4+ pages. Summary of what was retrievable — [EEVblog p1](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/); [p2](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/25/); [p3](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/50/); [p4](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/75/):
  - Schematics and layout are visual and spatial, which plays to LLM weaknesses. A **bird's-nest routing "would pass unnoticed by the AI, the simulator and the router alike."**
  - Several posters said doing the work by hand is faster than explaining it to an LLM.
  - A KiCad + Claude user on a moderately complex 4-layer board found Claude **very useful for checking** designs, but it did not produce the schematic or layout.
  - Another used Claude to review a 40+ page schematic, renumber about 1,200 components, and check net naming and power distribution. Claude found a **swapped IC pin** the original authors had missed.
  - Even with a datasheet and explicit instructions, Claude "still decided to hallucinate some junk."
  - One user had Claude write a routing program for an EAGLE board. The first Python version was slow and error-prone, and a C++ rewrite was much faster.
  - The kicad-happy skill pack was "very slow and not impressive, but clearly a lot of potential."
- **HN "Can AI design circuit boards yet?" (EEBench post, Sept 2026) [C].** — [HN](https://news.ycombinator.com/item?id=49569366); [EEBench blog](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)
  - One commenter: "LLMs completely break down" at routing. A rebuttal pointed to an EAGLE board routed by an LLM-written script, which a skeptic noted still had "dozens" of unrouted traces.
  - One user said they had tested "pretty much all available 'AI' board and schematic auto-layouters on the market. All failed even with the most basic tasks."
  - Another used "Sol" to design and route a board start to finish and got a working PCBWay prototype in a few weeks. Another found AI routing "usable" but still routes manually.
- **HN, placement vs. routing [C].** One commenter argued that writing a placement "cost function" is basically impossible when later steps add hard constraints. Another countered that conventional placement and routing algorithms work and the difficulty lies elsewhere. — [HN 47637631](https://news.ycombinator.com/item?id=47637631)
- **HN on Flux [C].** One user spent "50–100$ in tokens a couple of times" and "couldn't get more than a couple of simple components on the schematic". Another said "placement is probably the big issue that needs to be solved now." — [HN 48368721](https://news.ycombinator.com/item?id=48368721)
- **HN, KiCad 10 MCP thread [C].** AI was useful for schematics but did not handle placement or routing. — [HN 50085553](https://news.ycombinator.com/item?id=50085553)
- **KiCad forum, GPT-6 Astra thread (Sept 2026) [C].** — [KiCad forum](https://forum.kicad.info/t/open-ai-claims-gpt-6-astra-can-make-pcb-boards/71487)
  - Working on a PCB with an LLM is "like routing a board by describing it through text to an intern who has never used ECAD."
  - The OP said the model is "moderately good at PCB design but still very bad with high frequency signals, weak on HDI and BGAs."
  - Supporters cite **KiCad 11 headless mode and IPC API improvements plus MCP**, and argue that effective use requires giving the AI **deterministic tools to orchestrate**.
  - Several commenters said routing isn't the hard part; placement is "the hard problem."
- **Hackaday "Can AI Now Design PCBs That Just Work?" (Sept 5, 2026) [C].** — [Hackaday](https://hackaday.com/2026/09/05/can-ai-now-design-pcbs-that-just-work/); [Quilter commentary](https://www.quilter.ai/blog/llm-pcb-layout-gpt-6-astra)
  - Production boards still need edge-case handling, independent validation, and testing.
  - Hackaday's 2024 look at LLM PCB design concluded "you might as well just do it all by hand."
  - Commenters: AI "can make PCBs but it is very time consuming for complex designs"; LLMs are useful for layout tweaks and BOM consolidation, not one-shot design. One commenter vibe-coded three modest boards that worked on the first spin.
- **Windows-forum review of KiCAD-MCP-Server [C].** The tool "automates repetitive operations rather than designing boards". KiCad remains the authority, and Claude is an automation layer under supervision. Version the project before bulk changes. — [WindowsForum](https://windowsforum.com/windows-news.4/claude-for-kicad-automates-pcb-layout-but-needs-review.443300/)
- **Computer use (GUI screenshots and clicks):** I found **no documented experiment of Claude computer-use routing or placing in the KiCad GUI**. One how-to guide suggests computer use only for screen-bound checks like cross-probing a connector from schematic to PCB. — [Vagon guide](https://vagon.io/blog/how-to-use-kicad-with-claude-mcp-computer-use-guide-meta). The closest data point is NextPCB's GUI-only routing run: 3 segments in an hour. — [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test)

**Bugs reported by KiCad-MCP builders: what breaks under the hood [G]**

- **Rotation math:**
  - mcp-server-kicad used the textbook rotation matrix where KiCad uses the transpose, so **every footprint at a non-180° angle came back mirrored about its origin**. — [PR #59](https://github.com/ProductOfAmerica/mcp-server-kicad/pull/59)
  - Place, move, flip, and swap disagreed with KiCad's own transforms. Pad angles did not update, and footprint-owned zones landed near the board origin. — [issue #110](https://github.com/ProductOfAmerica/mcp-server-kicad/issues/110)
  - The fix consolidated everything into one orientation helper. — [PR #125](https://github.com/ProductOfAmerica/mcp-server-kicad/pull/125)
- **Schematic→PCB sync:** `pcb_sync_from_schematic` does not rotate child pad and field angles for rotated parts, which causes library-mismatch and silkscreen-overlap errors. — [kicad-mcp-pro #1319](https://github.com/oaslananka/kicad-mcp-pro/issues/1319)
- **Collision checks that disagree with KiCad:**
  - An overlap checker using a single **AABB per courtyard** flags parts sitting in the gap of multi-rectangle courtyards (for example MCU header modules), even though **KiCad's own DRC reports no violation**. — [KiCAD-MCP-Server #406](https://github.com/mixelpixx/KiCAD-MCP-Server/issues/406)
  - Courtyard-less footprints fall back to a pad-bounding-box approximation, which produces misleading "courtyard_overlap" warnings. — [kicad-tools #4227](https://github.com/rjwalters/kicad-tools/issues/4227)
- **Missing operations:**
  - No tool can move a placed footprint's Reference/Value text, so silkscreen-overlap warnings can't be fixed through MCP. — [Konnect #829](https://github.com/mixelpixx/Konnect/issues/829)
  - Copperhead added label coordinates to `move_footprint` after noting that **LLMs got the inverse rotation wrong for each part and angle**, leaving Reference labels clipping pads. — [Copperhead PR #398](https://github.com/copperheadhq/copperhead/pull/398)
- **KiCad itself:** KiCad gives no warning when a moved footprint overlaps a keepout area. — [KiCad GitLab #12594](https://gitlab.com/kicad/code/kicad/-/work_items/12594)

**Commercial AI layout tools in the field**

- **Flux AI Auto-Layout [V].**
  - Timeline: preview in Dec 2024 ("one-click routing" for simple and medium boards), open to all in Jan 2025, then a mid-2025 update with **net priority** and **@tools to direct Copilot**. Flux says it "works best when guided by thoughtful placement, clear net names, and rulesets". The Nov 2025 update claims shorter traces, fewer vias, and "paths that follow placement intent".
  - Docs: **existing traces and vias are treated as fixed obstacles**, so the engine only fills unrouted connections. Flux recommends **routing critical signals by hand first**, and each job costs credits based on complexity.
  - Sources: [Flux intro](https://www.flux.ai/p/blog/introducing-ai-auto-layout); [Flux update](https://www.flux.ai/p/blog/ai-auto-layout-just-got-smarter); [Flux winter update](https://www.flux.ai/p/blog/ai-auto-layout-winter-update); [Flux docs](https://docs.flux.ai/tutorials/auto-layout)
  - A competitor's view: Flux suits roughly 2–4-layer boards with 40–100 components, produces no physics "scorecard", and leaves diff pairs and high-speed interfaces to the engineer. — [Quilter comparison](https://www.quilter.ai/blog/the-2026-guide-to-autonomous-pcb-design-quilter-vs-deeppcb-vs-flux-ai)
- **Adafruit vs Flux [unverified].** A third-party page reports that on June 1, 2026, Adafruit said it had received a demand letter from Flux.ai's counsel threatening action if it published a review of Flux's AI tool, and the HN thread references an Adafruit review. I could not confirm this against an Adafruit primary post. If true, it is a notable chilling effect on independent evaluation. — [qwe.edu.pl summary](https://www.qwe.edu.pl/tutorial/adafruit-flux-ai-demand-letter-evaluate-ai-pcb-tools/); [HN 48368721](https://news.ycombinator.com/item?id=48368721)
- **DeepPCB vs Quilter, one user's 3-board test [A, published by a PCBA vendor].** DeepPCB completed about 10% more routes on average. On a **414-net board, DeepPCB left 12 nets unrouted and Quilter left 54**. Both still needed manual SI work: "AI doesn't know that this trace carries a sensitive analog signal." The time saved on prompts won't matter if the board fails DFM. — [DEV/AnyPCBA](https://dev.to/anypcba_official/i-let-ai-design-a-pcb-heres-how-it-went-5e41)
- **DeepPCB's own workflow [V]:** "pin the nets that need engineering judgment" so they stay hand-routed, and route the rest to your rules. DDR, length matching, advanced impedance, and RF constraints stay with engineers. — [DeepPCB](https://deeppcb.ai/); [JLCPCB tools list](https://jlcpcb.com/blog/ai-tools-for-pcb-design)
- **tscircuit [V/A].**
  - The official AI-prompting guide says: build a complete, readable **placement and netlist first**, run `tsci check placement`, **inspect the PCB image**, and fix overlaps or missing connections **before enabling routing**. — [tscircuit docs](https://docs.tscircuit.com/guides/circuit-generation/generating-circuit-boards-with-ai)
  - The VibePCB project generates with tscircuit and post-processes in KiCad. It notes systematic quirks in tscircuit's KiCad export and router, uses tscircuit's agent skill so the model doesn't invent props, and runs KiCad DRC/ERC. — [vibepcb](https://github.com/PaulBichl/vibepcb)
  - A tscircuit maintainer on HN said the hardest piece is LLM-compatible layout ("what I spend 90% of my time on"), and that they are building template-matching and heuristic layout, including "pack". (The exact thread URL was not confirmed; it surfaced alongside [HN 40751020](https://news.ycombinator.com/item?id=40751020) and [HN 44542880](https://news.ycombinator.com/item?id=44542880).)
  - Seve Ibarluzea proposes sequential optimal packing as an initial placement, refined by "hardening" constraints. He says "LLM loops can easily adapt the design intent representation", for example to keep a decoupling cap fixed next to its chip. He also notes that hand-specifying layout via group modes and coordinate expressions is "arduous for the user and inflexible as a design grows". — [autorouting blog](https://blog.autorouting.com/p/sequential-optimal-packing-for-pcb)

### Inferences
- The pattern that works is: **LLM writes intent or code → deterministic engine computes geometry → KiCad engines check → errors go back to the LLM**. Every board that succeeded followed it, and every report where the LLM pushed copper itself (GUI routing, hand-routing leftovers, label placement) shows slow progress or geometric mistakes.
- The most expensive failures are ones **the checkers cannot see**: wrong footprint variants (SOIC-8 wide vs SOP-8), parts underrated for voltage (78L05 at 36 V), and semantically wrong nets that pass ERC. A placer/router tool should ship **semantic checkers** (part–footprint–datasheet consistency, pin-by-pin netlist parity) in addition to DRC/ERC.
- Many failures are **tool bugs, not model bugs**: rotation transposes, AABB courtyards, same-name footprint collisions. If the tool's own geometry or checks diverge from KiCad's, the agent will chase phantom errors or miss real ones. The tool must reuse KiCad's own transforms and DRC.
- "Zero DRC" is a weak success signal. The thin power traces, sloppy loops, and "larger and less tidy" boards in these reports all passed DRC. Quality metrics (loop area, power-trace width vs current, decap distance) have to be reported separately.

### Gaps
- I found no systematic study of Claude computer use (screenshot plus click) operating the KiCad GUI, only the NextPCB GUI-only anecdote.
- Reddit threads (r/KiCad, r/PrintedCircuitBoard, r/ElectricalEngineering) did not surface in search, so Reddit field reports are missing.
- I found nothing on Diode Computers' public results or on Bluesky/X threads beyond one Seve post.
- The full text of the Tindie verdict, tinycomputers' "314 nets" lessons, and the Cherry Blossom failure taxonomy was not retrievable.
- The Adafruit/Flux review episode is unverified.

---

## 2. Published evaluations and demos with quantitative results

### Takeaway
Quantitative evidence is thin and mostly vendor-run. EEBench (run by atopile) is the closest thing to a public leaderboard, and it grades circuit design in code, with layout largely excluded according to the companion notes. On it, frontier agents score roughly 60–75%, and the scaffold matters a great deal. Layout-specific numbers are single-board anecdotes: unrouted counts, DRC counts, and parity-error counts. No independent benchmark of LLM-driven placement quality on real boards was found.

### Cited Findings
- **EEBench overall:**
  - The blog's answer to "Can AI design circuit boards yet?" is "some of them, yes" ("we still would not ask it to design a pacemaker and blindly install the result").
  - Working in **declarative atopile code "has worked much better for us than asking a model to draw lines in a GUI"**.
  - Sept 1, 2026 leaderboard: **Claude Opus 5 at 61.6%** across 13 tasks, with Grok 4.6 at 57.1%. — [EEBench blog](https://eebench.org/blog/can-ai-design-circuit-boards-yet/); [EEBench](https://eebench.org/)
- **EEBench, later snapshots:** GPT-6 Astra scored **69.3% (±10%)**, "in the same ballpark as Claude Opus 5, albeit cheaper and faster". Hackaday flags that EEBench is run by the atopile developers, a possible conflict of interest. — [Hackaday](https://hackaday.com/2026/09/05/can-ai-now-design-pcbs-that-just-work/)
- **EEBench, third-party mirror (Sept 29, 2026):**
  - The top entry is Claude Opus 5.5 at **75.0%**, then GPT-6 Astra at 69.3%. Claude Opus 5.5 also appears again at 68.9% with a different scaffold.
  - There are 38 model × scaffold configurations. Claude Sonnet 4.6 scored 20.4% and Gemini 3 Flash 19.5%.
  - **The scaffold (Claude Code / Codex CLI / Gemini CLI) is part of each entry.** — [BenchLM mirror](https://benchlm.ai/benchmarks/eebench). The duplicate row is an inconsistency in the mirror, so treat its numbers as provisional.
- **atopile vendor micro-benchmark [V]:** on a 70-component board, answering pin-sharing questions was **100% accurate through the code-based agent vs 55% from a schematic PDF**. — [atopile enterprise](https://atopile.io/enterprise)
- **Cherry Blossom, 40 boards [V]:** GPT-6 Astra ran "inside our own harness" across 40 drone, robotics, and sensor boards. **First-pass fab yield went from 94% to 97%**. They stress that **invented footprints are the costliest failure mode because nothing catches them until assembly**, and that a good result is "a reason to keep testing it, not a reason to ship it". — [Cherry Blossom](https://www.trycherryblossom.com/blog/gpt-6-astra-pcb-design)
- **OpenAI GPT-6 Astra demo [V, critiqued]:** a 15-second condensed playback of a 2 min 54 s run. Quilter notes that **no PCB-specific benchmark was published** and that the demo shows net completion, not board quality. — [Quilter](https://www.quilter.ai/blog/llm-pcb-layout-gpt-6-astra)
- **Single-board numbers (from §1):**
  - JLCPCB GPT-6 Astra: 46 parity issues. — [JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad)
  - EasyEDA: 50 mismatches across 120 pads. — [JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-easyeda-pro)
  - NextPCB: 3 segments per hour in GUI-only mode, and about 12 min via Freerouting orchestration. — [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test)
  - Blind test: 125→0 unrouted. — [GitHub](https://github.com/cyjjjj-21/gpt6-astra-kicad-blind-routing/blob/main/README.md)
  - Fable 5: 65 DRC errors on first pass, 49 left unrouted by Freerouting, and 1.25 s full route with KiCadRoutingTools. — [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/)
  - DeepPCB vs Quilter: 12 vs 54 unrouted on a 414-net board. — [DEV](https://dev.to/anypcba_official/i-let-ai-design-a-pcb-heres-how-it-went-5e41)
  - The companion notes also record 168 DRC violations vs 0 for a human board in one GPT-6 Astra test (see `llm_for_eda.md`, citing zerowithdot).
- **Autocuro "Can LLMs Verify PCB Designs?" (vendor, about late 2025) [V/A].**
  - Setup: ChatGPT and Gemini on two STM32 boards, a simple avionics board and the STM32L496G-DISCO.
  - Framing: full review means 200+ parameters across 11 verification phases.
  - Results: LLMs could review component placement **only when the user spent significant time creating labeled diagrams**, and they **struggled to interpret routing** and with spatial reasoning. — [Autocuro](https://autocuro.com/blog/can-llms-verify-pcb-designs)
- **JITX 2024 test of Gemini 1.5 Pro, GPT-4o, and Claude 3 Opus on expert PCB tasks [V].** Models were useful for building skills, writing code, and extracting datasheet data. Coverage reports that the best model (Claude 3 Opus) gave nonsensical filter suggestions, botched basic amplifier designs, struggled with component selection, and needed several passes to fix footprint generation. — [JITX blog](https://blog.jitx.com/jitx-corporate-blog/testing-generative-ai-for-circuit-board-design); [HN discussion](https://news.ycombinator.com/item?id=40751020)
- **Production LLM review agent [S, preprint]:** DRCY is a multi-agent LLM system that checks schematic connections **pin by pin against datasheets**, deployed in AllSpice Hub. Its authors note that existing EDA tools cannot verify that connections are semantically correct with respect to datasheets. — [arXiv 2603.15672](https://arxiv.org/pdf/2603.15672)
- **IEEE 2024 "AI in PCB Design: Insights from a Focused Case Study" [S, weak].** Nine AI PCB tools were analyzed from documentation, and only Flux.ai was tested hands-on because of access constraints. — [IEEE Xplore](https://ieeexplore.ieee.org/document/10631201)
- **A 2026 arXiv survey exists:** "Surveying GenAI-based Automation in Printed Circuit Board Design and Test". Its content was not retrieved. — [arXiv 2606.17074](https://arxiv.org/html/2606.17074v1)

### Inferences
- Benchmarks reward **getting the netlist right**, while field reports fail on **footprints, fab rules, and layout quality**. A placer/router project should define its own layout scorecard: unrouted count, DRC by severity, parity, footprint–datasheet consistency, loop areas, decap distance, power-trace ampacity, and via count. It should measure against human reference boards, as the blind-routing author did informally.
- Scaffold effects of up to roughly 50 points between harnesses on EEBench suggest that **tool and harness design matters as much as model choice**.

### Gaps
- There is no independent, multi-board benchmark of LLM-driven *placement* quality.
- The Cherry Blossom and JITX per-task breakdowns were not retrieved.
- I found no Quilter, DeepPCB, Diode, or JITX publication with controlled quantitative comparisons against human layouts in this session.

---

## 3. Tool designs that made LLM operation more reliable

### Takeaway
What worked in practice:
1. **Code/declarative or API representations** instead of GUI or raw-coordinate manipulation.
2. **Deterministic solvers for geometry** (packers, autorouters), with the LLM as orchestrator.
3. **Staged verification gates** in a fixed order: placement check and image, then routing, then DRC/ERC/parity.
4. **Using KiCad's own engines** for transforms and checks.
5. **Permission tiers, read-only defaults, Git workspaces, and human-gated release.**
6. **Grounding references**: agent skills and syntax references against invented props, plus datasheet and reference designs.
7. **Protecting critical nets**: hand- or agent-route them first, treat them as fixed obstacles, then autoroute the rest.

### Cited Findings
- **Code-first beats GUI:**
  - EEBench: declarative atopile code "worked much better than asking a model to draw lines in a GUI". — [EEBench blog](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)
  - vibe-hardware's PCB skill "generates KiCad by script (never the GUI files)" with a **severity-aware DRC gate**. — [vibe-hardware](https://github.com/luckiday/vibe-hardware)
  - tinycomputers: text-format boards that can be diffed, and a generator script. — [tinycomputers](https://tinycomputers.io/posts/redesigning-a-pcb-with-claude-code-and-open-source-eda-part-1.html)
  - atopile: 100% vs 55% on pin questions in code vs a PDF. — [atopile](https://atopile.io/enterprise)
- **GUI-level operation is very slow:** 3 trace segments per hour in GUI-only mode. — [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test)
- **Deterministic engines do the geometry:**
  - Astra's successful run was DSN → Freerouting → SES. — [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test)
  - Fable 5's board was finished by KiCadRoutingTools in 1.25 s. — [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/)
  - KiCadRoutingTools is a Rust-accelerated A* router, "~10× faster than pure Python", with diff pairs, length matching, planes, and "integration with AI driving tools". — [KiCadRoutingTools](https://github.com/atomic14/KiCadRoutingTools); [KiCad forum](https://forum.kicad.info/t/new-auto-router-plugin-kicadroutingtools/66877)
  - kicad-tools is "agent-first" with its own A* multi-layer router. — [DeepWiki kicad-tools](https://deepwiki.com/rjwalters/kicad-tools)
  - Forum consensus: give the AI "deterministic tools to orchestrate". — [KiCad forum](https://forum.kicad.info/t/open-ai-claims-gpt-6-astra-can-make-pcb-boards/71487)
- **Staged gates:** tscircuit orders the work as placement → `check placement` → inspect image → fix → enable routing. — [tscircuit docs](https://docs.tscircuit.com/guides/circuit-generation/generating-circuit-boards-with-ai). pcbkit runs DRC on pre-routes before Freerouting to avoid 900 s timeouts. — [pcbkit #2](https://github.com/bruk-io/pcbkit/issues/2)
- **Semantic and parity checks catch what ERC misses:** a pin-by-pin netlist comparison caught a net error that KiCad ERC missed. — [JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code). DRCY checks pin by pin against datasheets. — [arXiv 2603.15672](https://arxiv.org/pdf/2603.15672)
- **Permission tiers and progressive disclosure:**
  - kicad-mcp-pro defaults to **24 read-only review tools out of 377**. Write mode is for "controlled edits", release mode (manufacturing) is **human-gated**, and the expert/full catalog is for trusted clients only.
  - Its SI/PI/EMC/thermal tools are explicitly **closed-form estimates**, and ERC/DRC run through **KiCad's own engines**.
  - Sources: [kicad-mcp-pro](https://github.com/oaslananka/kicad-mcp-pro); [Glama listing](https://glama.ai/mcp/servers/zn01582wgi) (76.3% parity with KiCad's programmatically reachable surface)
- **Read-only start plus a Git-tracked folder:** [JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code). Version before bulk changes: [WindowsForum](https://windowsforum.com/windows-news.4/claude-for-kicad-automates-pcb-layout-but-needs-review.443300/)
- **Large tool surfaces are common but strain the agent.** Examples:
  - [Greg3001 kicad-claude-mcp](https://github.com/greg3001/kicad-claude-mcp) (105 tools)
  - [ProductOfAmerica mcp-server-kicad](https://github.com/ProductOfAmerica/mcp-server-kicad) (100+)
  - [Konnect](https://github.com/mixelpixx/Konnect) (217 tools by one listing, 228 by another; a beta Rust binary)

  Konnect is the successor to KiCAD-MCP-Server, whose Python/TypeScript design "hit limits" according to the maintainer, and its v0.13.0 release lists "safer placement". — [Konnect releases](https://github.com/mixelpixx/Konnect/releases)
- **Reuse KiCad's own transforms and checks (lessons from bugs):** rotation-transpose bug [PR #59](https://github.com/ProductOfAmerica/mcp-server-kicad/pull/59); single orientation helper [PR #125](https://github.com/ProductOfAmerica/mcp-server-kicad/pull/125); AABB vs KiCad DRC [#406](https://github.com/mixelpixx/KiCAD-MCP-Server/issues/406)
- **Don't ask the LLM to do inverse-rotation math:** Copperhead exposes **board-coordinate label placement** because LLMs got the inverse rotation wrong per part and angle. — [Copperhead PR #398](https://github.com/copperheadhq/copperhead/pull/398)
- **Grounding and syntax references:** VibePCB uses tscircuit's agent skill so the model doesn't invent props. — [vibepcb](https://github.com/PaulBichl/vibepcb). pcb-claude-plugin "asks a few questions, picks real parts, follows each chip's datasheet", then routes and runs checks. — [pcb-claude-plugin](https://github.com/virajrungta/pcb-claude-plugin)
- **Protect critical nets, then autoroute:** Flux treats existing copper as fixed obstacles and recommends routing critical signals first. — [Flux docs](https://docs.flux.ai/tutorials/auto-layout). DeepPCB has users "pin" judgment nets. — [DeepPCB](https://deeppcb.ai/)
- **Review and analysis skills as a separate layer:** kicad-happy (about 1.4k stars) analyzes schematics, layouts, and Gerbers, runs EMC pre-compliance and SPICE, and preps fab output. — [kicad-happy](https://github.com/aklofas/kicad-happy)
- **Visual feedback helps but needs labeled representations:**
  - LLMs reviewed placement only with labeled diagrams. — [Autocuro](https://autocuro.com/blog/can-llms-verify-pcb-designs)
  - In text-to-CAD, a **visual-feedback workflow performed best** among four agent workflows. — [Design Society paper](https://www.cambridge.org/core/journals/proceedings-of-the-design-society/article/from-text-to-design-a-framework-to-leverage-llm-agents-for-automated-cad-generation/5BD8D63CFCED28BDD7A01313162FFBE7)
  - tscircuit asks agents to inspect the PCB image. — [tscircuit docs](https://docs.tscircuit.com/guides/circuit-generation/generating-circuit-boards-with-ai)
- **Fab-rule configuration:** the Fable 5 board's critics asked whether DRC was ever set to JLCPCB rules. — [Lobsters](https://lobste.rs/s/yedfbj/this_pcb_is_brought_you_by_fable_5)

### Inferences
- The most valuable "tool design" is a **small set of high-level, semantic operations backed by KiCad's own geometry kernel**, plus **checkers that are the ground truth**. Large flat tool catalogs (100–377 tools) appear to work against reliability, and the most careful project (kicad-mcp-pro) exposes 24 by default.
- Undo/transactions and diffs are recommended in practice (Git folders, versioning before bulk changes), but I found no MCP server that reports **transactional apply/rollback** as a feature. This looks like an open design opportunity.

### Gaps
- No A/B evidence (same model, same board) compares high-level vs low-level tool APIs for PCB work. The support for "high-level ops" is indirect: EEBench, the bug reports, and NextPCB GUI vs Freerouting.
- No reports on token-limit failures on large boards turned up in search, though they are plausible.

---

## 4. Human–AI mixed-initiative design literature: what the HCI/design literature says about effective co-design tools that explain "why"

### Takeaway
The classic literature converges on a few principles:
- Automate where expected value beats inaction.
- Calibrate to uncertainty: ask, scope down, or act.
- Make invocation, dismissal, and correction cheap.
- Show *why*.
- Keep the designer's work primary, with suggestions beside it rather than overriding it.
- Offer **alternatives**, both local refinements and radically different options, rather than a single optimum.

Two warnings stand out. **Explanations raise acceptance whether or not the AI is right** (Bansal et al.), so explanations must be paired with verifiable evidence. And classic **design-rationale capture failed mainly on capture overhead and retrieval**, which an agent that logs its rationale automatically at decision time can avoid. Explainable optimization (XAI for OR/combinatorial optimization) is an active area but has not been applied to PCB placement in anything I found.

### Cited Findings

**Mixed-initiative principles**
- **Horvitz, "Principles of Mixed-Initiative User Interfaces" (CHI '99, pp. 159–166) [S]:**
  - The paper argues for coupling automated services with direct manipulation. Its running example is the Lookout scheduling system.
  - It addresses agents that guess poorly about user goals, weigh costs and benefits inadequately, and act at poor times.
  - It lists **12 principles**. The following list is reproduced from the paper; search snippets confirmed the count and the first items:
    1. Provide significant value-added automation.
    2. Consider uncertainty about the user's goals.
    3. Consider the user's attention when timing services.
    4. Infer the ideal action in light of costs, benefits, and uncertainties.
    5. Use dialog to resolve key uncertainties.
    6. Allow efficient direct invocation and termination.
    7. Minimize the cost of poor guesses about action and timing.
    8. Scope the precision of service to match uncertainty.
    9. Provide mechanisms for efficient agent–user collaboration to refine results.
    10. Use socially appropriate behaviors.
    11. Maintain working memory of recent interactions.
    12. Continue to learn by observing.
  - Act autonomously only when expected value exceeds inaction.
  - Sources: [Horvitz PDF](https://www.erichorvitz.com/chi99horvitz.pdf); [MSR page](https://www.microsoft.com/en-us/research/publication/principles-mixed-initiative-user-interfaces/); [Cambridge lecture](https://www.cl.cam.ac.uk/teaching/1819/P230/IWML-Lecture-3.pdf)
- **Amershi et al., "Guidelines for Human-AI Interaction" (CHI 2019) [S]:**
  - Method: 18 guidelines distilled from more than 150 recommendations and validated with UX/HCI experts. They are grouped by phase: initially, during interaction, when wrong, and over time.
  - The guidelines, from the paper:
    - **Initially:** make clear what the system can do; make clear how well it can do it.
    - **During interaction:** time services based on context; show contextually relevant info; match social norms; mitigate social biases.
    - **When wrong:** support efficient invocation; support efficient dismissal; support efficient correction; scope services when in doubt; **make clear why the system did what it did**.
    - **Over time:** remember recent interactions; learn from user behavior; update and adapt cautiously; encourage granular feedback; **convey the consequences of user actions**; provide global controls; notify users about changes.
  - Sources: [Amershi PDF](https://research.microsoft.com/%7Ehorvitz/Guidelines_Human_AI_Interaction.pdf); [MSR blog](https://www.microsoft.com/research/blog/guidelines-for-human-ai-interaction-design/)

**Interactive optimization with the designer in the loop**
- **Sketchplore / Sketchplorer (Todi, Weir, Oulasvirta; DIS 2016) [S]:**
  - Optimizers' "insistence on precise objectives and a point optimum is a poor fit with sketching practices."
  - The tool runs a real-time layout optimizer that **infers the designer's task** and searches for both **local improvements and global (radical) alternatives**.
  - Its suggestions appear **beside the canvas and never override the designer's work**.
  - The group later framed this work as mixed-initiative.
  - Sources: [Aalto record](https://research.aalto.fi/en/publications/sketchplore-sketch-and-explore-with-a-layout-optimiser/); [UHasselt PDF](https://documentserver.uhasselt.be/bitstream/1942/21793/1/ea3780-todi.pdf)
- **Computational design with humans in the loop:** a CHI 2021 course by Koyama et al. on computational design methods. Only its existence is confirmed here. — [Koyama course part 3](https://koyama.xyz/courses/chi2021-computational-design/download/part3.pdf)

**Generative design and presenting alternatives**
- **Dream Lens (Matejka et al., Autodesk Research, CHI 2018) [S].** Generative design produces "hundreds or thousands" of candidates that all meet the criteria, and judging them requires structural and aesthetic analysis. Dream Lens maps thousands of solutions to a 2D space for navigation. The paper includes two studies and a public dataset of 16,800 designs. — [Autodesk Research](https://research.autodesk.com/publications/dream-lens-exploration-and-visualization-of-large-scale-generative-design-datasets/); [PDF](https://research.autodesk.com/app/uploads/2023/03/dream-lens-exploration-and.pdf_recFfqgLe5eOFLays.pdf)
- **GEM-NI (CHI 2015):** a system for creating and managing alternatives in generative design. Details were not verified. — [DOI](https://dx.doi.org/10.1145/2702123.2702398)
- **Generative design's effect on the designer's role [S].** Saadi & Yang (ASME J. Mech. Des. 2023) ran a grounded-theory interview study of six designers (mechanical, architecture, industrial) with more than 5 years of experience. The specific findings were not retrieved. — [ASME](https://asmedigitalcollection.asme.org/mechanicaldesign/article/145/4/041411/1156493/Generative-Design-Reframing-the-Role-of-the)
- **Fusion generative design in practice [A].** The software returns candidates that are valid for the inputs, while choosing among them, applying engineering judgment, and adapting for assembly stay with the engineer. — [practitioner guide](https://uk.getrenewedtech.com/2025/02/08/fusion-360-generative-design-letting-the-software-optimise-your-parts/). Setting up the design space requires a different approach from conventional CAD. — [Cormack study](https://cormack.xyz/GenerativeDesign/)

**CAD copilots and text-to-CAD (2025–2026)**
- **CADTests (arXiv 2605.07807) [S].** Claude models detected about 65% of CAD mutants. **Topological, dimensional, volumetric, and spatial requirements** were the hardest to satisfy, which mirrors the spatial weakness seen in PCB work. — [arXiv](https://arxiv.org/pdf/2605.07807)
- **Design Society text-to-CAD framework [S].** Five LLMs and four agent workflows were tested, and **visual feedback performed best**. — [Cambridge Core](https://www.cambridge.org/core/journals/proceedings-of-the-design-society/article/from-text-to-design-a-framework-to-leverage-llm-agents-for-automated-cad-generation/5BD8D63CFCED28BDD7A01313162FFBE7)
- **Related titles (only the titles were seen):**
  - "Clarify Before You Draw: Proactive Agents for Robust Text-to-CAD Generation". — [arXiv 2602.03045](https://arxiv.org/pdf/2602.03045)
  - "Self-Improving CAD Generation Agents with Finite Element Analysis as Feedback". — [arXiv 2605.17448](https://arxiv.org/pdf/2605.17448)

**Trust calibration and explanation effects**
- **Bansal et al., "Does the Whole Exceed its Parts?" (CHI 2021) [S].** With an AI of roughly human accuracy, team performance did exceed either alone, but **explanations did not add to that gain**. **Explanations increased acceptance of AI recommendations whether or not they were correct.** The authors call for explanations that foster *appropriate* trust. — [arXiv 2006.14779](https://arxiv.org/abs/2006.14779); [CHI PDF](https://aiweb.cs.washington.edu/ai/pubs/bansal-chi21.pdf)
- **Engineers' trust in AI output (2026 survey, general engineering) [V/survey]:** of 400+ engineering professionals and students, **86% use AI tools but only 6% trust AI-generated results without hesitation**, and nearly 9 in 10 verify outputs. — [Allwork.space on Omni Calculator survey](https://allwork.space/2026/02/86-of-u-s-engineers-use-ai-but-only-6-fully-trust-it-2026-survey-finds/)
- **Automation bias among novices [A]:** "it's very reassuring to get green light from LLM." — [HN](https://news.ycombinator.com/item?id=44542880)

**Explainable optimization (XAI for OR / combinatorial optimization)** — citation level only; full texts were not read.
- De Bock, Coussement, De Caigny et al., "Explainable AI for operational research: a defining framework, methods, applications, and a research agenda", *EJOR* 317(2):249–272, 2024.
- Erwig & Kumar, "Explanations for combinatorial optimization problems", *J. Computer Languages* 79:101272, 2024.
- Aigner et al., "A framework for data-driven explainability in mathematical optimization", AAAI 2024.
- Goerigk & Hartisch, inherently interpretable optimization models, EJOR 2023.
- Forel, Parmentier & Vidal, "Explainable data-driven optimization: from context to decision and back again", ICML 2023.
- These references surfaced in — [arXiv 2412.01264](https://arxiv.org/pdf/2412.01264)
- A 2025 paper links decision information with LLMs for "explainable OR". — [arXiv 2502.09994](https://arxiv.org/pdf/2502.09994)
- A 2026 survey groups post-hoc explanation into feature subsets, feature attribution, prototypes, and global surrogates. It concerns explaining ML predictors, not optimizer decisions. — [arXiv 2607.07762](https://arxiv.org/pdf/2607.07762)

**Design-rationale capture (IBIS, QOC, and why it failed)**
- **Karsenty, "An Empirical Evaluation of Design Rationale Documents" (CHI '96) [S]:** with six professional designers, **only 41% of their questions about a past design were answered by the captured rationale**. — [ACM DL](https://dl.acm.org/doi/fullHtml/10.1145/238386.238462)
- **Barriers to adoption [S]:**
  - Capture **overhead** and interruption of creative flow are the central problem.
  - IBIS had early industrial successes that did not lead to widespread adoption.
  - IBIS's localized arguments and lack of context make **retrieval from large records hard**, and managing many IBIS issues or QOC diagrams is difficult.
  - Sources: [Buckingham Shum, QOC retrieval](https://www.semanticscholar.org/paper/QOC-Design-Rationale-Retrieval:-A-Cognitive-Task-Shum/65037a32d6bb6d068f773edab54adf6d567d2dca); [15 years on from gIBIS and QOC](https://www.researchgate.net/publication/42790084_Hypermedia_support_for_argumentation-based_rationale_15_years_on_from_gIBIS_and_QOC); [Decision Cards](https://link.springer.com/chapter/10.1007/978-3-319-67744-6_29); [IBIS history](https://eight2late.com/2009/07/08/the-what-and-whence-of-issue-based-information-systems/); [Design rationale overview](https://en.wikipedia.org/wiki/Design_rationale)

**Intent-based layout specification**
- Seve Ibarluzea argues that coordinate-expression and group-mode layout specification is "arduous" and "inflexible as a design grows". He proposes a **design-intent representation** (for example, "decap fixed next to chip") that LLM loops can edit, with a packer that hardens constraints. — [autorouting blog](https://blog.autorouting.com/p/sequential-optimal-packing-for-pcb)

### Inferences
- **An LLM agent fixes the main reason design rationale failed.** Rationale was too costly for humans to write, but an agent can record an IBIS/QOC-style record (Issue → Options → Criteria → Decision → Evidence) *for free* at the moment it acts. The retrieval problem Karsenty and Buckingham Shum found suggests attaching rationale to **board objects** (a footprint, net, zone, or constraint), so "why is C12 here?" is answered in context, not from a separate document.
- **Bansal's result is a warning for PCB tools.** A fluent "I placed C12 here to minimize loop area" will be believed whether or not it is true. Explanations should cite **checkable evidence**: a measured loop area, a DRC rule ID, a datasheet page, a before/after metric delta. They should also say **what was not checked**, for example "SI estimated with a closed-form model only", following kicad-mcp-pro's labeling.
- **Sketchplore and Dream Lens point toward showing a few (2–4) structurally different placements** with their tradeoff metrics, plus local tweaks, instead of one "optimal" board. This matches how DeepPCB, Flux, and expert workflows already let humans lock the parts they care about.

### Gaps
- I found no peer-reviewed HCI study of **PCB designers** using an AI layout co-pilot, and no study of XAI applied to PCB/IC placement decisions.
- I found no user studies of Zoo Text-to-CAD or Onshape AI with engineers. Only benchmark-style evaluations surfaced.
- The trust-specific findings of the generative-design interview study (Saadi & Yang) were not retrieved.
- "Intent-based CAD" as a named literature did not surface. The closest material is atopile/tscircuit declarative intent and Seve's packing post.

---

## 5. How expert PCB designers want AI help: surveys, polls, and top concerns

### Takeaway
Adoption of *some* AI tooling is near-universal in 2026 surveys. Designers mainly want an **acceleration layer inside existing workflows**, such as real-time error detection, review, and drudgery removal, not fully autonomous layout. The recurring concerns are **trust and auditability** (decades of bad autorouters), **quality on high-speed/RF/HDI**, **IP security**, and **losing control**. Systematic, independent survey data specific to PCB designers and AI is scarce. The main 2026 survey is vendor-sponsored.

### Cited Findings
- **Weidmuller USA / EETech National PCB Design Survey (400 North American engineers, Apr–May 2026) [V-sponsored survey]:**
  - **More than 9 in 10 have used AI-based tools** in their PCB workflow.
  - **75% see AI as a productivity and acceleration layer within existing workflows**, with faster iteration as the main current value.
  - Write-in gaps: a lack of **real-time error detection** and of **fully autonomous text-to-PCB**.
  - Sources: [Automation World](https://www.automationworld.com/analytics/news/55393457/weidmuller-pcb-design-survey-reveals-ai-tool-impacts); [Weidmuller press](https://www.weidmuller.com/en/company/press/trade_press_news/pcb_design_survey/index.jsp); [Designing Electronics](https://www.designing-electronics.com/weidmuller-usa-releases-new-national-pcb-design-survey-engineers-share-insights-on-pcb-design-tools-ai-tool-impacts-gaps/)
- **General engineering trust:** 86% use AI, 6% trust it without hesitation, and about 90% verify. — [Allwork.space](https://allwork.space/2026/02/86-of-u-s-engineers-use-ai-but-only-6-fully-trust-it-2026-survey-finds/)
- **Unverified IPC figure:** an AtlasPCB article cites a Feb 2026 IPC survey reporting a 30% reduction in design-to-tapeout time with only modest first-pass gains. I could not find the IPC source. — [AtlasPCB](https://www.atlaspcb.com/news/news-ai-pcb-design-tools-cadence-altium-ml-2026/)
- **Trust and quality concerns (trade press) [C/V]:** many engineers question whether AI can match human quality, and IP security is a concern. — [PCD&F](https://pcdandf.com/pcdesign/index.php/current-issue/289-best-practices/18594-ai-in-pcb-design-it-s-already-here)
- **Autorouter distrust is historical and specific [V]:**
  - Commercial autorouters have shipped in Allegro, Altium, Xpedition, and others, and engineers "have, just as consistently, learned not to trust them." — [DeepPCB](https://deeppcb.ai/the-autorouter-broke-your-trust-heres-whats-actually-different-now/)
  - Professionals *do* use interactive automation (push-and-shove, length tuning) but not "route the whole board for me". Many reject automation "not because they hate speed, but because they **cannot audit the output**." — [Quilter 2026 review](https://www.quilter.ai/blog/the-2026-automated-pcb-layout-software-review-ai-vs-autorouters-vs-manual-design); [Quilter autorouter post](https://www.quilter.ai/blog/pcb-autorouter-was-the-right-idea)
- **Where designers draw the line [C]:** practitioners generally keep high-frequency/RF, HDI/BGA, EMI-sensitive, and novel analog work for themselves. — [KiCad forum](https://forum.kicad.info/t/open-ai-claims-gpt-6-astra-can-make-pcb-boards/71487); [DeepPCB scope via JLCPCB list](https://jlcpcb.com/blog/ai-tools-for-pcb-design). A vendor guide frames the realistic deliverable as "a reviewable first draft in minutes… not a signed-off design." — [ProtoFlow](https://www.protoflow.ai/blog/ai-pcb-design-2026-guide)
- **Where experienced users find value today [C]:** checking and review (swapped pins, net naming, power distribution, renumbering), datasheet lookups, and scripting. Layout is not on the list. — [EEVblog](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/25/); [HN](https://news.ycombinator.com/item?id=49569366)
- **Industry editorial framing:**
  - Design007's Jan 2025 "Designer of the Future" issue asked whether designers would use AI throughout the cycle. — [I-Connect007](https://iconnect007.com/article/143676/january-2025-issue-of-design007-magazine-the-designer-of-the-future/143673/design); [PDF](https://magazines007.com/pdf/Design007-Jan2025.pdf)
  - I-Connect007 describes AI suggesting layouts, placements, and routing paths. — [I-Connect007](https://iconnect007.com/article/141418/the-new-chapter-artificial-intelligence-in-pcb-design/141415/pcb)
  - APEX EXPO 2026 coverage previewed AI in design tools as "much more than the dreaded auto-router." — [PCB007 magazine page](https://iconnect007.com/magazines/pcb-magazine)

### Inferences
- The demand signal ("real-time error detection", "acceleration within existing workflows", "cannot audit the output") favors a **co-pilot that proposes, explains, and verifies inside KiCad**, with human-lockable regions. A batch "auto-everything" button is the wrong primary interface, though autonomous modes can exist for simple boards.
- "Auditability" is the explicit requirement. That argues for per-step diffs, scorecards, and object-anchored rationale (see §6).

### Gaps
- I found no Altium, Cadence, Siemens, Zuken, or IPC primary survey on AI in PCB design in this session.
- I found no academic interview study of PCB layout professionals about AI (an IEEE case-study paper exists, but it is a tool review).
- The Weidmuller survey's full question breakdown (trust items, specific concerns) was not retrieved.

---

## 6. Implications for an LLM-driven KiCad placer/router

### Takeaway
Build the system as a **mixed-initiative orchestrator**. The LLM handles intent, constraints, sequencing, triage, and explanation. Deterministic, KiCad-native engines handle geometry, routing, and checks. A human-facing layer shows alternatives, diffs, scorecards, and object-anchored rationale backed by checkable evidence. Every recommendation below traces to a failure or success in §1–§5.

### Cited Findings (evidence base for the recommendations)
- LLM-pushed geometry fails or crawls: 3 GUI segments per hour [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test); inverse-rotation errors on labels [Copperhead #398](https://github.com/copperheadhq/copperhead/pull/398); rotated connectors [HN](https://news.ycombinator.com/item?id=49695689)
- Tool-side geometry and checks diverge from KiCad: [PR #59](https://github.com/ProductOfAmerica/mcp-server-kicad/pull/59), [#110](https://github.com/ProductOfAmerica/mcp-server-kicad/issues/110), [#406](https://github.com/mixelpixx/KiCAD-MCP-Server/issues/406), [#1319](https://github.com/oaslananka/kicad-mcp-pro/issues/1319)
- Deterministic routers finish what LLMs can't: [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/), [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test). The router choice matters: Freerouting plateaued, KiCadRoutingTools took 1.25 s. Pre-route DRC prevents 900 s stalls: [pcbkit #2](https://github.com/bruk-io/pcbkit/issues/2)
- Invisible failures: footprint variants [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/), [Cherry Blossom](https://www.trycherryblossom.com/blog/gpt-6-astra-pcb-design); semantic nets past ERC [JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code); parity [JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad)
- Staged gates [tscircuit](https://docs.tscircuit.com/guides/circuit-generation/generating-circuit-boards-with-ai); tiers and human-gated release [kicad-mcp-pro](https://github.com/oaslananka/kicad-mcp-pro); Git workspace [JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code)
- Net completion ≠ quality [Quilter](https://www.quilter.ai/blog/llm-pcb-layout-gpt-6-astra); "zero DRC" boards were still criticized [HN](https://news.ycombinator.com/item?id=44542880), [blind test](https://github.com/cyjjjj-21/gpt6-astra-kicad-blind-routing/blob/main/README.md)
- Mixed-initiative, alternatives, and explanation research: [Horvitz](https://www.erichorvitz.com/chi99horvitz.pdf), [Amershi](https://research.microsoft.com/%7Ehorvitz/Guidelines_Human_AI_Interaction.pdf), [Sketchplore](https://research.aalto.fi/en/publications/sketchplore-sketch-and-explore-with-a-layout-optimiser/), [Dream Lens](https://research.autodesk.com/publications/dream-lens-exploration-and-visualization-of-large-scale-generative-design-datasets/), [Bansal](https://arxiv.org/abs/2006.14779), [Karsenty](https://dl.acm.org/doi/fullHtml/10.1145/238386.238462)
- Designers want acceleration inside existing workflows and auditable output: [Weidmuller survey](https://www.automationworld.com/analytics/news/55393457/weidmuller-pcb-design-survey-reveals-ai-tool-impacts), [Quilter review](https://www.quilter.ai/blog/the-2026-automated-pcb-layout-software-review-ai-vs-autorouters-vs-manual-design)

### Inferences (concrete design principles; these are my synthesis, not sourced claims)

**A. Tool API (what the LLM can call)**
1. **No raw-coordinate math in the model.** Expose *relational, semantic* placement ops, and let the tool compute all transforms with KiCad's own code (pcbnew / IPC API) through a single orientation helper. Examples:
   - `place_near(ref, anchor=U1.pin("VDD"), max_dist_mm, side)`
   - `align(refs, axis)`
   - `orient_pin_toward(ref, pin, target)`
   - `place_in_zone(refs, zone)`
   - `keep_together(group)`
   - `fix(ref)`

   Raw `set_position(x, y, θ)` can exist for experts, but the agent should rarely need it. Include operations for **silkscreen and reference text in board coordinates**.
2. **The tool computes the geometry; the LLM writes the intent.** The agent should write **constraints** (proximity, keep-outs, grouping, net classes, critical-loop membership, "pin these nets"). A packer or placer and a router (KiCadRoutingTools, Freerouting, or an internal solver) solve them. The LLM can edit the constraint set between solver runs, following Seve's "hardening" loop.
3. **Ground truth comes from KiCad engines only.** DRC, courtyard collision, zone fill, and connectivity should come from KiCad itself, not re-implemented approximations such as AABB courtyards. Set **fab-specific DRC rules first** (JLCPCB, PCBWay profiles) as a mandatory precondition.
4. **First-class semantic checkers beyond DRC/ERC:**
   - `check_footprint_vs_part(ref)`: pad count, pitch, body width, package variant vs MPN/datasheet. This catches the SOIC-8 wide vs SOP-8 class of error.
   - `netlist_parity()`: schematic ↔ PCB pin-by-pin.
   - Component ratings vs net voltage and current (the 78L05 at 36 V case).
   - Layout-quality metrics: decap-to-pin distance, switching-loop area, power-trace width vs expected current, diff-pair skew, return-path continuity, unrouted count, via count.
5. **Small, curated, tiered tool surface.** Start read-only (inspect, measure, check). Unlock a few write ops with explicit modes, and gate manufacturing outputs behind human approval. Avoid flat catalogs of 100–377 tools. Use progressive disclosure.
6. **Transactions and diffs.**
   - Every write call runs inside a transaction that returns a **structured diff**: objects moved, nets changed, metric deltas, and DRC delta.
   - The agent can `commit` or `rollback`.
   - Snapshot to Git automatically per committed step, and support `compare(snapshot_a, snapshot_b)`.
7. **Pre-flight checks before expensive solvers.** Run DRC on pre-routed copper before autorouting. Set **timeouts and plateau detection**, and return partial results with the reason, such as "stalled at 49 unrouted; blocking region near U3".
8. **Perception tools sized for LLMs.** Return compact text or JSON summaries (per-net status, per-region congestion, top-N violations with object IDs and coordinates). Provide **labeled renders** (refdes, net highlights, violation markers, region crops) as a secondary channel for review, not as the primary state.

**B. Agent loop**
1. **Plan → constrain → place (solver) → placement gate → route critical → autoroute rest → DRC/parity/quality gate → triage → repeat**, with a fixed **iteration budget** and stall detection. This guards against the "endless routing loops" failure.
2. **Critical-first routing.** The agent (or human) routes or locks power loops, crystals, diff pairs, and sensitive analog first. They become fixed obstacles, and the autorouter handles the rest. This mirrors Flux, DeepPCB, and Astra workflows.
3. **Error triage over error count.** Sort DRC output by severity and root cause, and fix root causes first (a misplaced part causing 20 clearance errors). Keep a **regression ledger** so fixes don't reintroduce earlier errors.
4. **Separate reviewer pass.** A second agent or rule pack (kicad-happy/DRCY-style) reviews against datasheets and reference designs. The builder should not self-certify.
5. **Use reference designs.** When a vendor reference layout exists (RP2350, ESP32, regulator datasheets), retrieve it and use it as a placement template or constraint source.
6. **Escalate under uncertainty** (Horvitz #5/#8, Amershi "scope services when in doubt"). Ask the human about ambiguous intent: connector edge, mechanical constraints, which nets are sensitive. Do this before running long solver jobs, not after.
7. **Scale management for big boards.** Work hierarchically (per sheet, functional block, or region) with summaries instead of full S-expression dumps. Never load the whole `.kicad_pcb` into context.

**C. Human-facing UX and explanation of choices**
1. **Suggestions beside the canvas, never silent overwrites** (Sketchplore). Provide one-click accept, reject, or tweak, and **lock** controls for parts, regions, and nets that the agent must respect. These are Amershi's efficient invocation, dismissal, correction, and global controls.
2. **Alternatives, not a single answer.** Offer 2–4 structurally different placements (for example "connector-left / compact", "thermal-spread", "shortest critical loops") with a **scorecard comparison**, plus local refinements of the chosen option (Dream Lens, Sketchplore).
3. **A scorecard on every proposal.** Show unrouted count, DRC by severity, parity, footprint checks, loop areas, decap distances, power-trace ampacity, via count, and board area. Compare against the previous step and, if available, a reference design. Net completion alone is never presented as success.
4. **Object-anchored, evidence-backed rationale.** Every agent decision writes a compact IBIS/QOC-style record attached to the affected objects:
   - **Issue:** decoupling for U3 VDD.
   - **Options considered:** C12 at the top side near pin 4; C12 on the bottom via-in-pad.
   - **Criteria:** loop area, assembly side, DRC.
   - **Decision and evidence:** a measured loop area, a datasheet page citation, a rule ID, and the metric delta.

   Clicking a part or net answers "why here?" and "why not there?". The contrastive answer comes from re-running the solver with the alternative and showing the delta. Rationale captured this way costs the designer nothing and is retrievable in context, which addresses the documented DR failure modes.
5. **Explanations calibrated against Bansal's warning.** Mark each claim as **verified** (KiCad DRC, measured), **estimated** (closed-form SI/thermal), or **unverified** (heuristic or LLM judgment). Show what was *not* checked, and never let fluent prose substitute for a check result. For novice users especially, avoid a single green "looks good" verdict; show the residual risk list instead.
6. **Diff-first review.** Each agent step appears as a visual and textual diff (moved parts, rerouted nets, metric changes) that can be reverted individually. Release outputs (Gerbers, pick-and-place) require an explicit human sign-off step.
7. **Interruptibility and pacing** (Horvitz #3/#6). Long solver runs show progress and can be stopped. The agent batches questions at natural checkpoints (after the placement proposal, before autorouting) rather than interrupting continuously.

### Gaps
- None of these principles has been A/B tested on PCB tasks in the literature I found. They are extrapolated from field reports, GitHub bug trails, and general HCI findings.
- Specifically, no PCB study measured whether alternatives, scorecards, or object-anchored rationale improve designer outcomes or trust calibration. That would be a valuable evaluation for this project.
