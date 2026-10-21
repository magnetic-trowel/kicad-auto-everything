# Field reports: LLM agents driving KiCad and other EDA tools

**TL;DR**
- By late 2026 many Claude- or GPT-driven boards have been fabricated and worked first time. They share a pattern:
  - simple, mostly digital, 2–4 layers;
  - **the LLM orchestrated deterministic engines** (Freerouting, KiCadRoutingTools, scripts);
  - KiCad ERC/DRC plus **independent read-back or parity checks** were fed back;
  - a human or the fab DFM caught the rest.

  [P, anecdote]
- Wherever the LLM pushed copper directly (GUI routing, hand-routed leftovers, a self-written grid router), progress was slow or geometrically wrong [P, anecdote].
- **The best large-board result** (about 370 footprints, 6 layers, DRC-clean) came from a **library of deterministic, measurable moves**, not from more LLM freedom [P].
- LLMs add real value at the **noticing** level: congestion clusters, datasheet mismatches. They do not add value in computing exact coordinates [P, anecdote].

## Key facts

### End-to-end case studies

| Report | Setup | What happened | Source |
|---|---|---|---|
| **A6M-Zero**, "brought to you by Fable 5" (Sept 2026) | Fable 5 via a KiCad MCP, autonomous for a couple of hours; 5-line prompt (RP2350, e-ink, buttons) | Opus 4.8 earlier was "terrible… no idea about the orientation of the components". First pass: 65 footprints, 54 nets, 118 unconnected, **65 DRC errors**. W25Q128JVS (SOIC-8 wide) put on SOP-8 pads ("it insisted that there was a SOP-8 package"); caught only at the JLCPCB preview. Freerouting plateaued with 49 left; **KiCadRoutingTools routed all in 1.25 s**. 4 layers, 31.8 × 37.32 mm, €130 for 5 assembled; enumerated over USB first time. "Front: beautiful placement… Back: horrendous tracks"; "not feeling much of an accomplishment" | [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/) [P, anecdote] |
| **tinycomputers**, "Routing 314 nets" | Python-generated pcb-rnd board (155 × 90 mm, ten SN74LVC8T245, 72 channels) plus Freerouting | Claude noticed unrouted nets clustered and proposed staggering U6–U10 → **314/314 on 4 layers**. A datasheet audit caught a DIR-pulldown bug that "the same LLM… introduced". 121 false-positive DRC flags (same-net junctions) took about 6 h; the fab DFM found real issues. A save bug produced 5 copper layers and Claude "happily kept trying to fix it". About 18 h in total. Lessons: dry-run the pipeline on a toy board; run DRC with several tools and compare; treat the fab DFM as truth; unit-test the generator ("net X has pins Y and Z"); stop when a fix fails a second or third time. Verdict: "a competent junior collaborator… no physical intuition" | [tinycomputers](https://tinycomputers.io/posts/what-routing-314-nets-taught-me-about-ai-assisted-pcb-design.html) [P, anecdote] |
| **JLCPCB, KiCad MCP + Claude Code** (Oct 2026) | XL4015 5 A buck, 16 nets, 63 × 33 mm, kicad-mcp-pro (read-only default) | Design review before the schematic fixed 4 errors (VC tied to GND, a 30 V-rated 78L05 on 36 V, etc.). **7 issues**: LM358 units stacked; multi-unit wiring needed a patch; an ISENSE–ISET short from overlapping labels where **ERC only warned** (caught by netlist comparison); FB beside SW (fixed with a 1.2 mm keepout); **Claude wrote its own A\* router** (0.1 mm grid), with 0.35 vs 0.5 mm edge clearance giving 7 DRC; part search unreliable; **placement batch ran twice**. Silkscreen script: 47 → 2 warnings. "Zero DRC errors… does not confirm that the schematic matches your intent" | [JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code) [V/anecdote] |
| **JLCPCB, Claude Opus 5.5 in EasyEDA Pro** | Official API skill (about 120 classes, 62 enums, 70 interfaces) | 47 parts, 3 pages, 71.1 × 50.8 mm, 33/33 nets, 0 DRC. **Read-back of 138/138 pins found 6 missing GNDs** behind API success; attributes silently lost; the DRC API returns **counts only**; `importChanges()` waits for a human click; Freerouting `-mt 1` plus `check_ses.py` "open nets 0"; a human approved 8 substitutions; "Claude Code did not directly see the PCB layout" | [JLCPCB](https://jlcpcb.com/blog/claude-code-pcb-design) [V/anecdote] |
| **JLCPCB, GPT-6 Astra in KiCad** | TPA3116D2 amplifier, 45 footprints, 120 pads | "Lock the critical supply, bootstrap, and switching copper first… then refill zones and confirm the locked copper survived". **46 parity issues** (mostly fields) fixed in source data; 9 DRC/ERC categories ignored ("part of the result"); a 120 pin-pad independent check; portability re-check. **Routing was reused from an earlier task** | [JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad) [V/anecdote] |
| **JLCPCB, GPT-6 Astra in EasyEDA** | Same board | Asked one clarifying question (speaker impedance). The import "looked plausible" yet had **50 association mismatches over 120 pads** because the shared name `C0603` aliased in the device cache; fixed by unique names | [JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-easyeda-pro) [V/anecdote] |
| **NextPCB**, Astra routing test | Fixed placement | Unrestricted: about 12 min via DSN → Freerouting → SES. GUI-only: **3 short segments in an hour**. "Calling an autorouter is not the same as becoming one". Two runs, one board | [NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test) [P, anecdote] |
| **Tindie** (gongyu) | ESP32-S31 robot head from reference PDFs | GPT-5.6 schematic "hard to read" until redrawn with library symbols. Astra: 13-block hierarchy, **9 unrouted nets**, antenna keepout needs work. Saves "well over half" of initial time; workflow "essentially open-loop" | [Tindie](https://blog.tindie.com/2026/09/i-designed-a-kicad-pcb-with-gpt-5-6-and-gpt-6-and-it-changed-how-i-think-about-hardware-design/) [P, anecdote] |
| **StationX** "HAL" | 555 badge in <1 h, KiCad 10 | Chose TLC555 over NE555 (3 V); via 0.0285 mm from a pad; courtyard violations; 150.4% duty-cycle sim error; battery polarity "logged… as reasoning, not as a sourced fact"; 5 DRC → 0. "Keep the AI's inferences labelled as inferences"; "give it zero discretion in verification" | [StationX](https://app.stationx.net/articles/ai-pcb-design) [P, anecdote] |
| **MakeUseOf** | Claude Code + mixelpixx KiCAD-MCP | Outlines, holes, arrays, net classes and DRC worked; "Claude will get the component footprints wrong from time to time"; needs KiCad vocabulary; Pro-plan rate limits | [MakeUseOf](https://www.makeuseof.com/pcb-design-easier-thanks-to-claude/) [P, anecdote] |
| **KiCad Agentic MCP** (nevenfo) | Regulator plus 2 caps, twice | 5 → 0 unconnected both times, but **different coordinates**; KiCad ops <1 s vs 6–7 min of AI. Reply: "I would have done a better layout… faster than typing that prompt" | [forum](https://forum.kicad.info/t/kicad-agentic-mcp-an-ai-assistant-that-edits-your-board-through-kicads-own-api-and-lets-kicad-decide-whether-the-result-is-good/71403) [P, anecdote] |
| **RF workflow paper** | Claude Fable 5 in Claude Code; GNSS L1 antenna, about 2 h; CST, ADS, KiCad 9 via pcbnew and kicad-cli | Netlist-identical by construction (75 nodes, 18 nets). RF lines were drawn as copper polygons replicating the simulated line models; knowledge was kept in agent-maintained markdown, with standing conventions. Human review caught rounded line ends, a missing 45° miter, solder-mask openings, and a tee vs crossing; first schematic "not human-readable" | [2608.31006](https://arxiv.org/abs/2608.31006) [P] |
| atomic14 (Jul 2025) | Claude Code + atopile | Components left unwired; EN RC missing its cap; layout by hand | [atomic14](https://atomic14.substack.com/p/vibe-coding-a-pcb-surprisingly-good) [S] |

### Long-form tool-builder logs
- **nexatech kicad-agent-toolkit:** a dense 6-layer mixed-signal board (about 370 footprints, about 1,700 pads) taken to a DRC-clean release; "over a hundred failures, each with its symptom, cause and the rule that came out of it". Key lessons are in [field-failure-modes.md](field-failure-modes.md) and [agent-tooling-reliability-patterns.md](agent-tooling-reliability-patterns.md) ([lessons](https://raw.githubusercontent.com/nexatech-ltd/kicad-agent-toolkit/main/docs/lessons-learned.md)) [P].
- **haohao kicad-clean-pcb:** the first attempt "passed DRC" with about **10,000 zigzag segments** and 4 pours. The restructured board had about 600 segments, 30 vias, one GND plane and a third less area. A 1:1 paper check, done too late, found a blocked USB port, a wrong fuse-holder pitch and a duplicate terminal block. That led to a 7-stage, 4-checkpoint workflow ([README](https://github.com/haohao-0725/PCB_Layout_with_AGENT_in_KiCAD)) [P].
- **Gato513/kicad-mcp:** validated to 63 footprints / 48 nets / 2 layers. On the 437-footprint HackRF the autorouter did not complete: Freerouting 2.1.0 crash-looped for an hour, and `add_zone(fill=true)` can crash KiCad after 3–4 calls ([README](https://github.com/Gato513/kicad-mcp)) [P].
- **KiCadRoutingTools (atomic14):** a Rust A* router (about 10× faster than Python [S]). `/plan-pcb-routing` turns Claude's plan into GUI parameters plus a checkable step list, saved as JSON and replayable with no Claude call ([README](https://github.com/atomic14/KiCadRoutingTools)) [P].

### Computer use vs API
- No documented Claude computer-use KiCad GUI layout experiment was found. The only GUI-only data point is NextPCB's 3 segments per hour [P].
- JLCPCB: computer use makes the model "a user of KiCad because it lacks its own routing engine and design rule checker" [V].
- EEBench: a GUI agent's context is "coordinates, menus and application state" [V].

### Practitioner sentiment (condensed)
- **EEVblog:** Claude helps most with review and checking; a bird's-nest routing "would pass unnoticed by the AI, the simulator and the router alike" [S].
- **KiCad forum:** "like routing a board by describing it through text to an intern"; "give it deterministic tools to orchestrate" [S].
- **Hackaday "Em":** three vibe-coded PCBs worked; "routing can look a little wonky" ([zerowithdot](https://zerowithdot.com/blog/gpt-6-astra-impact-on-cad/)) [P].

Full forum mining lives in the practice cluster's workflow docs.

## Recommendations for our system

1. **Architecture:** the LLM handles intent, code and orchestration; deterministic engines handle geometry; KiCad and the fab give the verdict; independent read-back confirms what was written [I].
2. **Expose congestion and failure attribution** so the LLM can contribute at the "noticing" level.
3. **Put readability and mechanical-fit gates before routing.** DRC-clean ≠ usable: think of 10,000 zigzags, a blocked USB port.
4. **Publish limits honestly,** as Gato513 does ("where it stops working *before* they hit it").

## Conflicts and open questions

- GitHub issue threads were only seen as snippets.
- Altium Academy's "168 vs 0" is video-only.
- Diode's "Sonnet 4.5 preferred 8/10" and the Adafruit/Flux demand-letter episode are unverified.

## Sources
- research notes: [field_reports_and_ux.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)
- related: [llm_for_eda.md § 1 (RF workflow, industry demos)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)

See also: [field-failure-modes.md](field-failure-modes.md), [agent-tooling-reliability-patterns.md](agent-tooling-reliability-patterns.md), [designer-demand-and-trust.md](designer-demand-and-trust.md), [../workflow/llm-field-reports.md](../workflow/llm-field-reports.md) (forum-sourced complement), [../kicad/mcp-server-lessons.md](../kicad/mcp-server-lessons.md)
