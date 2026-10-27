# LLM-driven circuit design

Can an LLM go from a plain-language brief to a schematic that is correct, not only well-formed? We tried it with a typed circuit IR, deterministic checks and KiCad round trips, then had a second LLM review each design. The tool held; the designs did not pass review.

| Path | Status | One-line result | Page | Code |
|---|---|---|---|---|
| Typed circuit IR → checked KiCad schematic, `.kicad_dru` and placement intent (kaesynth) | worked (as a tool) | 4 designs build with 0 unwaived errors, clean ERC and exact netlist round trip | [kaesynth.md](kaesynth.md) | `tools/research/llm-design/synth/` |
| Four LLM-made designs with independent LLM review | partial | every review "not ready": 0–2 blockers and 4–7 majors per design, mostly invisible to the checks | [kaesynth.md](kaesynth.md#results) | `tools/research/llm-design/designs/` |
| Survey: schematic generation and part selection (others' work) | survey | code/typed IR beats raw `.kicad_sch` generation; ERC is a low bar | [schematic-generation-landscape](../../topics/synthesis/schematic-generation-landscape.md), [part-selection-and-verification](../../topics/synthesis/part-selection-and-verification.md) | — |

Related areas: [placement](../placement/README.md) (the intent files are meant to feed a placer; not done yet), [research index](../README.md).
