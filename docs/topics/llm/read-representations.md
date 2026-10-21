# What the LLM reads: encodings, code vs GUI, tool granularity

**TL;DR**
- Graph encoding choice alone swings accuracy by **4.8–61.8%**. Use an **incident list** (each part with its pins, nets and neighbours) and stable short ids [P].
- A **compact hierarchical JSON plus query tools** beats native KiCad exports and PDFs: **0.88 vs 0.55 vs 0.43** accuracy on PCB-QA [P].
- **Never have the LLM read or write raw `.kicad_pcb` S-expressions as its working format.** Relative, pin-name code gives 82.0% valid circuits against 32.5% for raw KiCad files [P].
- Code and API access beats GUI computer use: GUI-only routing produced 3 segments in an hour; orchestrated routing finished in about 12 minutes [P, anecdote].
- KiCad operations take milliseconds while an LLM turn takes minutes, so expose **coarse, high-yield operations** [P, anecdote].

## Key facts

### Encodings

| Finding | Number | Source |
|---|---|---|
| Graph text encoding changes accuracy | 4.8–61.8% | Talk like a Graph, ICLR 2024 [P] ([2310.04560](https://arxiv.org/abs/2310.04560)) |
| Incident list vs edge list, connected-node query | **53.8% vs 19.8%** | same; integer node names help arithmetic |
| CSS-style left/top/width/height exemplars | "most essential component" of the prompt | LayoutGPT, NeurIPS 2023 [P] ([2305.15393](https://arxiv.org/abs/2305.15393)) |
| Cell-aligned integer grid encodings | +30–40 pp on some puzzles, −26 pp on others | TopoBench [P] ([2603.12133](https://arxiv.org/abs/2603.12133)) |
| Formal language choice (4 languages, 6 LLMs) | affects syntactic and semantic reasoning | [2502.17216](https://arxiv.org/abs/2502.17216) [P] |
| Multi-hop relative chains | accumulate frame-transform errors; fix with global-to-local re-parameterization | R³L [P] ([2605.06758](https://arxiv.org/abs/2605.06758)) |
| ASCII "mental images" (Visualization-of-Thought) | +23.5% on grid navigation; prompt-sensitive | [2404.03622](https://arxiv.org/abs/2404.03622) [P] |

**PCB-QA** [P] ([2606.23704](https://arxiv.org/abs/2606.23704), MLCAD 2026): 480 yes/no questions over 8 KiCad projects.

| Input format (GPT-5.4 Nano) | Accuracy | F1 |
|---|---|---|
| KiCad-exported PDF | 0.43 | 0.28 |
| Native `.net` + `.cir` | 0.55 | 0.45 |
| **Hierarchical JSON** | **0.88** | **0.90** |

With JSON, Gemini 3 Flash reaches 93% on the full set. Inputs reach about 100k tokens on complex projects, so Python helper tools filter the relevant subcircuits and nets.

**SchGen** [P] ([2605.30345](https://arxiv.org/abs/2605.30345)), GPT-oss-20B + LoRA. Its APIs use "local coordinate systems with relative offsets from anchor components and connect wires by semantic pin names".

| Configuration | Valid | Functional | Netlist Jaccard |
|---|---|---|---|
| Relative/pin-name code | **82.0%** | 60.5% | 49.1 |
| Same model, raw KiCad files | **32.5%** | 3% | 9.1 |
| Code without CoT | 53.4% | 14% | — |
| Vanilla GPT-oss | 11.0% | — | — |
| GPT-5.2, code prompt | 67.9% | — | — |
| GPT-5.2, raw KiCad text | 10.5% | — | 0.53 |

On the out-of-distribution set, SchGen reached 65.6% valid against GPT-5.2's 77.0%, with fewer overlaps (7.46 vs 12.12) and equal Jaccard. Large models "often use relative coordinates… even if the prompt example code does not".

**PCBWorld's LLM observation** [P] (verification note):
- an S-expression such as `(net 1 "NET1" (pads (pad D0 10.000 10.000 1) …))`;
- the static board block sits in the system message, for prefix caching;
- the per-step message holds the routing geometry, the router head, a 2-turn history, rejected attempts and the valid verbs;
- zones are dropped, rules collapse to the strictest netclass, and coordinates are rounded to 3 decimals.

See [../routing/pcbworld.md](../routing/pcbworld.md).

### Code and API vs GUI

- **GUI-only routing:** after one hour, "only three short trace segments". The same board routed in about 12 min via DSN → Freerouting → SES ([NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test)) [P, anecdote].
- **EEBench:** code "has worked much better for us than asking a model to draw lines in a GUI". A GUI agent's context fills with "coordinates, menus and application state" ([EEBench](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)) [V].
- **Diode:** "Schematics for humans, code for models" ([Diode](https://blog.diode.computer/anthropic-partnership)) [V].
- **JITX:** a text-native representation ([JITX](https://blog.jitx.com/jitx-corporate-blog/testing-generative-ai-for-circuit-board-design)) [V]. atopile claims pin-sharing questions are answered 100% correctly from code vs 55% from a PDF [V, snippet].
- **PCBEditor:** computer use "is the slowest possible path… not reproducible… for hardware… usually disqualifying"; Python scripting with an assistant is "the most underrated option" ([DEV](https://dev.to/dibyaprakash_pradhan/kicad-and-ai-in-2026-mcp-servers-scripts-and-what-actually-works-3p1a)) [V].
- No documented Claude computer-use experiment placing or routing in the KiCad GUI was found.
- **Design as code:**
  - The RF workflow drove KiCad 9 only through pcbnew and kicad-cli. Schematic and layout were "netlist-identical by construction", and all 75 nodes and 18 nets were checked automatically ([2608.31006](https://arxiv.org/abs/2608.31006)) [P].
  - kicad-pycbnew (MIT) writes `.kicad_pcb` files with no KiCad runtime, with constraint-driven routing, track arrays and via grids ([2609.27522](https://arxiv.org/abs/2609.27522)) [P].

### Tool granularity, latency, scale

- **Latency:** in the KiCad Agentic MCP demo, KiCad operations took under 1 s while the full AI interaction took about **6–7 min**. Coordinates differed between two runs ([forum](https://forum.kicad.info/t/kicad-agentic-mcp-an-ai-assistant-that-edits-your-board-through-kicads-own-api-and-lets-kicad-decide-whether-the-result-is-good/71403)) [P, anecdote].
- **Catalog size:** catalogs run from 105 to 377 tools; kicad-mcp-pro defaults to **24 read-only tools** [P].
- **Truncation:** list results are capped with `_total` and `_truncated` metadata, and narrow per-list tools are recommended ([havamal-65/KiCad-MCP](https://github.com/havamal-65/KiCad-MCP)) [S].
- **Scale:** a compact board-state encoding was validated only up to 63 footprints ([Gato513](https://github.com/Gato513/kicad-mcp)) [P].
- **Pad names:** viewer data that dropped pad names left agents unable to map REFDES:PIN (HTMLPCBViewer #90) [S].
- **Harness cost:** coding-agent harnesses cost 2.2–5.4× the tokens of native calls (RAC) [P].
- **RTL-to-GDS:** "low-level tool-interface mismatches are a major source of failures" ([2607.17528](https://arxiv.org/abs/2607.17528)) [P].

## Recommendations for our system

1. **Read state** [I]:
   - parts with stable short ids, footprint class, size class, side and locked flag;
   - an **incident-list netlist** (each pin with its net, datasheet role and connected parts);
   - net classes and criticality tags;
   - **tool-computed facts**: groups, overlaps, unrouted connections, DRC items with object ids, per-relation verdicts with margins.
2. **Query tools rather than dumps:** `neighbors(pin)`, `nets_of(ref)`, `path(a, b)`, `pins_by_role`, plus truncation metadata.
3. **Working representation:** an anchor-relative DSL with pin-name references, with chains anchored directly to IC or module frames. Never raw `.kicad_pcb` (see [interfaces-relations-vs-coordinates.md](interfaces-relations-vs-coordinates.md)).
4. **Coarse operations:** "place block under relations", "route these nets protecting locked copper", "verify locked copper plus zone refill".
5. **Prefix-cache static board context** in the system message.
6. **Code and API only;** no GUI computer use for geometry.

## Conflicts and open questions

- No PCB head-to-head exists comparing JSON, S-expression, ASCII, SVG and image representations.
- No A/B exists comparing coarse and fine tool APIs on KiCad.
- Cell-aligned encodings help some tasks and hurt others; this needs testing on PCB tasks.

## Sources
- research notes:
  - [llm_for_eda.md § 2, § 3, § 8A](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
  - [netlist_datasheet_understanding.md § 1, § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/netlist_datasheet_understanding.md)
  - [learning_from_layout_data.md § Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md)
  - [field_reports_and_ux.md § 1B, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)
  - [verification_papers.md § 2.1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [vision-feedback.md](vision-feedback.md), [spatial-reasoning-limits.md](spatial-reasoning-limits.md), [../ux/agent-tooling-reliability-patterns.md](../ux/agent-tooling-reliability-patterns.md), [../kicad/mcp-server-lessons.md](../kicad/mcp-server-lessons.md)
