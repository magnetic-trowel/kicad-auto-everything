# What the LLM reads: encodings, code vs GUI, tool granularity

Scope: input representation for the LLM (graph encodings, formats, code vs GUI access, tool granularity and latency). Not here: write interface -> [interfaces-relations-vs-coordinates](interfaces-relations-vs-coordinates.md); images -> [vision-feedback](vision-feedback.md); MCP server practice -> [kicad/mcp-server-lessons](../kicad/mcp-server-lessons.md), [ux/agent-tooling-reliability-patterns](../ux/agent-tooling-reliability-patterns.md).
Keys: read state, graph encoding, incident list, edge list, Talk like a Graph, hierarchical JSON, PCB-QA, SchGen, relative code, raw .kicad_pcb, S-expression, PCBWorld observation, prefix cache, GUI computer use, code vs GUI, design as code, kicad-pycbnew, tool granularity, coarse operations, truncation, latency

## Read-state design

[I]
1. Read state: parts with stable short ids, footprint class, size class, side, locked flag; **incident-list netlist** (each pin with its net, datasheet role, connected parts); net classes and criticality tags; **tool-computed facts**: groups, overlaps, unrouted connections, DRC items with object ids, per-relation verdicts with margins.
2. Query tools, not dumps: `neighbors(pin)`, `nets_of(ref)`, `path(a, b)`, `pins_by_role`, with truncation metadata.
3. Working representation: anchor-relative DSL with pin-name references, chains anchored directly to IC or module frames (avoids R³L multi-hop errors). Never raw `.kicad_pcb` S-expressions.
4. Coarse operations, since KiCad operations take milliseconds and an LLM turn minutes: "place block under relations", "route these nets protecting locked copper", "verify locked copper plus zone refill".
5. Prefix-cache static board context in the system message.
6. Code and API only; no GUI computer use for geometry.

## Encodings

| Finding | Number | Source |
|---|---|---|
| Graph text encoding changes accuracy | 4.8–61.8% | Talk like a Graph, ICLR 2024 [P] ([2310.04560](https://arxiv.org/abs/2310.04560)) |
| Incident list vs edge list, connected-node query | **53.8% vs 19.8%**; integer node names help arithmetic | same |
| CSS-style left/top/width/height exemplars | "most essential component" of the prompt | LayoutGPT, NeurIPS 2023 [P] ([2305.15393](https://arxiv.org/abs/2305.15393)) |
| Cell-aligned integer grid encodings | +30–40 pp on some puzzles, −26 pp on others (untested on PCB) | TopoBench [P] ([2603.12133](https://arxiv.org/abs/2603.12133)) |
| Formal language choice (4 languages, 6 LLMs) | affects syntactic and semantic reasoning | [2502.17216](https://arxiv.org/abs/2502.17216) [P] |
| Multi-hop relative chains | accumulate frame-transform errors; fix with global-to-local re-parameterization | R³L [P] ([2605.06758](https://arxiv.org/abs/2605.06758)) |
| ASCII "mental images" (Visualization-of-Thought) | +23.5% on grid navigation; prompt-sensitive | [2404.03622](https://arxiv.org/abs/2404.03622) [P] |

## PCB-QA input formats

[P] ([2606.23704](https://arxiv.org/abs/2606.23704), MLCAD 2026): 480 yes/no questions over 8 KiCad projects.

| Input format (GPT-5.4 Nano) | Accuracy | F1 |
|---|---|---|
| KiCad-exported PDF | 0.43 | 0.28 |
| Native `.net` + `.cir` | 0.55 | 0.45 |
| **Hierarchical JSON** | **0.88** | **0.90** |

With JSON, Gemini 3 Flash reaches 93% on the full set. Inputs reach ≈100k tokens on complex projects, so Python helper tools filter relevant subcircuits and nets.

## SchGen relative code vs raw KiCad

[P] ([2605.30345](https://arxiv.org/abs/2605.30345)), GPT-oss-20B + LoRA; APIs use "local coordinate systems with relative offsets from anchor components and connect wires by semantic pin names".

| Configuration | Valid | Functional | Netlist Jaccard |
|---|---|---|---|
| Relative/pin-name code | **82.0%** | 60.5% | 49.1 |
| Same model, raw KiCad files | **32.5%** | 3% | 9.1 |
| Code without CoT | 53.4% | 14% | — |
| Vanilla GPT-oss | 11.0% | — | — |
| GPT-5.2, code prompt | 67.9% | — | — |
| GPT-5.2, raw KiCad text | 10.5% | — | 0.53 |

Out-of-distribution: SchGen 65.6% valid vs GPT-5.2 77.0%, fewer overlaps (7.46 vs 12.12), equal Jaccard. Large models "often use relative coordinates… even if the prompt example code does not".

## PCBWorld LLM observation

[P] (verification note) -> [routing/pcbworld](../routing/pcbworld.md): S-expression such as `(net 1 "NET1" (pads (pad D0 10.000 10.000 1) …))`; static board block in the system message for prefix caching; per-step message holds routing geometry, router head, 2-turn history, rejected attempts, valid verbs; zones dropped, rules collapsed to the strictest netclass, coordinates rounded to 3 decimals.

## Code and API vs GUI

- GUI-only routing: after one hour "only three short trace segments"; same board routed in ≈12 min via DSN -> Freerouting -> SES ([NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test)) [P, anecdote].
- EEBench: code "has worked much better for us than asking a model to draw lines in a GUI"; a GUI agent's context fills with "coordinates, menus and application state" ([EEBench](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)) [V].
- Diode: "Schematics for humans, code for models" ([Diode](https://blog.diode.computer/anthropic-partnership)) [V].
- JITX: text-native representation ([JITX](https://blog.jitx.com/jitx-corporate-blog/testing-generative-ai-for-circuit-board-design)) [V]. atopile claims pin-sharing questions answered 100% correctly from code vs 55% from a PDF [V, snippet].
- PCBEditor: computer use "is the slowest possible path… not reproducible… for hardware… usually disqualifying"; Python scripting with an assistant "the most underrated option" ([DEV](https://dev.to/dibyaprakash_pradhan/kicad-and-ai-in-2026-mcp-servers-scripts-and-what-actually-works-3p1a)) [V].
- No documented Claude computer-use experiment placing or routing in the KiCad GUI found.
- Design as code [P]: RF workflow drove KiCad 9 only through pcbnew and kicad-cli; schematic and layout "netlist-identical by construction", all 75 nodes and 18 nets checked automatically ([2608.31006](https://arxiv.org/abs/2608.31006)). kicad-pycbnew (MIT) writes `.kicad_pcb` with no KiCad runtime, constraint-driven routing, track arrays, via grids ([2609.27522](https://arxiv.org/abs/2609.27522)).

## Tool granularity, latency, scale

- Latency: KiCad Agentic MCP demo, KiCad operations < 1 s, full AI interaction ≈**6–7 min**; coordinates differed between two runs ([forum](https://forum.kicad.info/t/kicad-agentic-mcp-an-ai-assistant-that-edits-your-board-through-kicads-own-api-and-lets-kicad-decide-whether-the-result-is-good/71403)) [P, anecdote].
- Catalog size: 105–377 tools; kicad-mcp-pro defaults to **24 read-only tools** [P] -> [kicad/mcp-server-lessons](../kicad/mcp-server-lessons.md).
- Truncation: list results capped with `_total` and `_truncated` metadata; narrow per-list tools recommended ([havamal-65/KiCad-MCP](https://github.com/havamal-65/KiCad-MCP)) [S].
- Scale: compact board-state encoding validated only up to 63 footprints ([Gato513](https://github.com/Gato513/kicad-mcp)) [P].
- Pad names: viewer data that dropped pad names left agents unable to map REFDES:PIN (HTMLPCBViewer #90) [S].
- Harness cost: coding-agent harnesses 2.2–5.4× the tokens of native calls (RAC) [P].
- RTL-to-GDS: "low-level tool-interface mismatches are a major source of failures" ([2607.17528](https://arxiv.org/abs/2607.17528)) [P].

## Open questions

- No PCB head-to-head of JSON, S-expression, ASCII, SVG and image representations.
- No A/B of coarse vs fine tool APIs on KiCad.

## Sources
- [llm_for_eda.md § 2, § 3, § 8A](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
- [netlist_datasheet_understanding.md § 1, § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/netlist_datasheet_understanding.md)
- [learning_from_layout_data.md § Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md)
- [field_reports_and_ux.md § 1B, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)
- [verification_papers.md § 2.1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
