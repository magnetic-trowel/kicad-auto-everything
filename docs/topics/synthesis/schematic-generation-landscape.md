# Schematic generation: prior art and KiCad output

Scope: tools, papers and field runs that generate schematics; KiCad 9/10 `.kicad_sch` writer pitfalls; our writer and parity-gate design. Not here: part choice, checks beyond ERC, placement intent -> [part-selection-and-verification.md](part-selection-and-verification.md).
Keys: schematic generation, SKiDL, schematizer, atopile, tscircuit, Diode Zener, circuit-synth, kicad-sch-api, JITX, Flux, CELUS, Circuit Mind, boardforge, skidl-skills, PCBSchemaGen, PCBBench, OSE, pcbGPT, SchGen, HWE-Bench, CircuitLM, EEBench, Schemato, Weave, EEschematic, MultModLM, AnalogCoder, Masala-CHAI, SINA, Netlistify, labels-only, netlist parity gate, `lib_symbols`, `instances`, UUIDv5, PWR_FLAG, `SEXPR_SCHEMATIC_FILE_VERSION`, 20250114, 20260306

Tags: [P] primary (paper, docs or source read); [S] snippet/secondary; [V] vendor claim; [I] inference. Repositories read as of 2026-10-22; research done 2026-10-23.

## Code-first tools and commercial generators

Every open system that reaches a board has the LLM write code or a typed IR; a deterministic writer emits KiCad [P]. Our typed-IR plan has that shape [I].

| Tool | Representation | Parts: chosen and checked | Checks | Output, readability | Licence; activity |
|---|---|---|---|---|---|
| **SKiDL** 3.0.0 | Python netlist DSL: parts, pins by name/alias, nets, buses, subcircuits, part and net classes | KiCad symbols; `skidl-part-search` (SQLite index); no MPN/stock check | ERC with pin types and drive strength; SPICE via PySpice | Netlist, PCB, SPICE; schematics (KiCad 6–10) delegated to schematizer since 3.0.0 | MIT; 2026-10-16 ([history](https://github.com/devbisme/skidl/blob/master/HISTORY.md)) [P] |
| **schematizer** 0.2.0 | Generic hierarchical JSON netlist with embedded symbol graphics | — | none | `.kicad_sch` or SVG. Default mode places and routes **randomly each run, no seed**. `labels` mode: grid placement, stub + power symbol or label on every pin, one sheet per subcircuit, ≈2 s for 190 parts | MIT; first released 2026 ([PyPI](https://pypi.org/project/schematizer/)) [P] |
| **atopile** | Declarative `ato`: modules, typed interfaces, units, tolerances, `assert`; set-valued parameter solver | Parametric pick **only R, C, L** from hosted API (`components.atopileapi.com`) within solved bounds; others by LCSC ID via `atopile-easyeda2kicad` | `requires_pulls`; power-bus voltage aliasing; current summing; constraint consistency | **`.kicad_pcb` only**, no `.kicad_sch` (graph viewer); sub-module layouts reused as groups | MIT, but required `atopile-easyeda2kicad` is **AGPL-3.0**. PyPI 0.15.9 (2026-09-12); public `main` last commit 2026-03-11 ([repo](https://github.com/atopile/atopile)) [P] |
| **tscircuit** | React/TSX → Circuit JSON | JLCPCB parts via community jlcsearch API [S] | Source DRC; SPICE and IBIS elements | Own schematic, PCB, autorouter. Layout modes `match-adapt` (graph matched against a corpus of drawn layouts), grid, flex, matchpack; trace solver; net labels. `circuit-json-to-kicad` writes `20250114` | MIT; near-daily (0.0.3006 on 2026-10-22) ([core](https://github.com/tscircuit/core)) [P] |
| **Diode Zener / `pcb`** | Starlark DSL; typed nets (`Power`, `Ground`); modules; interfaces | KiCad symbol libraries; package registry | `TestBench` with circuit-path and component-sequence matchers | KiCad 10 layout; schematic preview, placement persisted in comment blocks | MIT ([repo](https://github.com/diodeinc/pcb)) [P] |
| **circuit-synth** + **kicad-sch-api** | Python `@circuit` functions | KiCad library search; JLCPCB lookups via Claude Code agents | KiCad ERC | `.kicad_sch`, **net label on every pin** + hierarchical labels; kicad-sch-api targets KiCad 7/8 | MIT; 0.12.1 (2026-01-09), 0.5.6 (2025-11-19); slowing [P] |
| **JITX** (Python 4.x; Stanza before 4.0) | Python API | `jitxlib.parts` query API [V] | Design constraints [V] | Auto-drawn: wires inside a `SchematicGroup`, **net labels where wires cross groups**; connectivity not editable in GUI ([docs](https://docs.jitx.com/en/4.0/api/jitx.circuit.html)) [P] | Proprietary |
| **Flux** | Browser EDA + agent | Own library, price, stock, datasheet reading [V] | AI review, FMEA, DRC [V] | Places and wires in own format ([docs](https://docs.flux.ai/reference/copilot.md)) | Proprietary; no accuracy claims |
| **CELUS** | Requirements → CUBO function blocks | Curated CUBO catalog with lifecycle | not published | Schematic + BOM; KiCad export with library package; no layout ([KiCad export](https://www.celus.io/blog/kicad-libraries-exportpackage)) [V] | Proprietary |
| **Circuit Mind** ACE | Requirements → variables, constraints → solver ([US 12,050,847 B2](https://patents.google.com/patent/US12050847)) [P] | Own database | "Independent rule checks"; claims error-free output [V] | Schematic + BOM [V] | Proprietary |
| **boardforge** / **skidl-skills** | Multi-agent Claude Code pipeline writing SKiDL | pcbparts MCP (JLCPCB parametric, Mouser/DigiKey stock); `kipart` symbols from datasheet pin tables | Independent ERC-reviewer agent; `kicad-cli` parity; ngspice review gate | schematizer `labels` → parity → pcbnew placement → Freerouting | MIT ([boardforge](https://github.com/devbisme/boardforge), [skidl-skills](https://github.com/devbisme/skidl-skills)) [P] |

- Diode: in blind comparisons of generated reference designs, Diode engineers preferred Sonnet 4.5 over Opus 4 (60:40) and over Sonnet 4 (82:18); testbenches grade requirements ("≥22 µF between power and ground"), not exact parts ([Anthropic](https://claude.com/blog/making-claude-a-better-electrical-engineer)) [V].
- Not generators: Quilter and DeepPCB consume an existing schematic and board ([quilter](../landscape/quilter.md), [deeppcb](../landscape/deeppcb.md)); Cadstrom ("Sigma Engine", $6.8M seed) and AllSpice DRCY review designs [S]/[V]. Commercial context: [commercial-incumbents-and-startups](../landscape/commercial-incumbents-and-startups.md).
- Readable vs exact: writers either auto-place and draw wires (schematizer, tscircuit, JITX, Weave) or write labels only (exact by construction). Wire-drawing writers have shipped shorts (→ [field evidence](#field-evidence-one-prompt-nine-tools)) [P].
- Reuse **schematizer** (MIT) `labels` mode as the first `.kicad_sch` backend: emit its JSON netlist from our IR, one sheet per functional block; pretty layouts are a later optional view [I].
- Take ideas, not packages: atopile set-valued parameters with tolerances, bus parameters that alias voltage and sum current, `requires_pulls`; Diode topology test benches; Weave equivalence certificates; pcbGPT valid-pin-list errors ([tools table](part-selection-and-verification.md#how-tools-keep-parts-real-and-pinouts-right)) [I].
- Do not ship atopile as a dependency: its required LCSC importer is AGPL-3.0 and its picker needs a hosted API key ([reuse-matrix](../licensing/reuse-matrix.md)) [I].

## Papers and benchmarks, 2024–2026

| Work | Task, representation | Correctness check | Result | Code |
|---|---|---|---|---|
| **PCBSchemaGen** ([2602.00510](https://arxiv.org/html/2602.00510v2), v2 Jun 2026) | Spec + required ICs → SKiDL. Per-IC datasheet knowledge graph (KG): 32-role pin ontology, 4 predicate templates (`supply_pair`, `must_be_connected`, `driving_pair`, `diff_pair_distinct`), ≈300 tokens/IC, 47 ICs | 5-layer verifier: ERC; pin-role net matching; subcategory templates; VF2 topology signatures; power invariants; errors localized to pins. κ = 0.91 vs senior engineers; 6.7% false accept | Pass@1 (4 calls), PCBBench (62 tasks): GPT-5.4 94.0, Gemini 3.1 Pro 94.3, Gemma-4-31B 81.3. Held-out OSE (165 tasks): GPT-5.4 79.3, Gemma 69.8. Circuitron-style prompting baseline 41.9 / 20.7 | MIT ([repo](https://github.com/HZou9/PCBSchemaGen_v2)) [P] |
| **pcbGPT** ([2606.01188](https://arxiv.org/html/2606.01188), KIT/Bosch) | Chat → Python DSL → KiCad project; `FlexiblePin` for interchangeable pins | Execute → ERC → separate LLM validator against datasheet summaries | 20 tasks: GPT-5.3-Codex pass@1 0.90 (hard 0.72); GPT-5.1 0.60 (hard 0.12). Failure rate vs component count r = 0.863 | not stated [P] |
| **SchGen** ([2605.30345](https://arxiv.org/html/2605.30345v1)) | NL → schematic code, anchor-relative placement, pin-name wiring; fine-tuned GPT-oss-20B | Code runs and KiCad ERC has zero critical errors; netlist Jaccard; 2 experts | 82.0% valid / 60.5% functional vs 32.5% / 3.0% for raw KiCad text, same model. GPT-5.2: 50.0% functional | — [P]; detail: [read-representations](../llm/read-representations.md) |
| **HWE-Bench** ([2603.18102](https://arxiv.org/html/2603.18102)) | Requirements + 2,914 datasheets → board netlist; **model selects parts**; 300 tasks | Static pin and protocol checks, then LTspice transient vs ground-truth testbench | Fully correct: Claude Sonnet 4.5 8.15%, GPT-5.2 6.58%, Gemini 3.1 Pro 5.16%, Grok-4 4.40% | [P] |
| **CircuitLM** ([2601.04505](https://arxiv.org/abs/2601.04505), ICLAD 2026) | NL → CircuitJSON, grounded in curated component KB with canonical pinouts | Deterministic ERC with severity classes + LLM judge | 100 prompts × 5 LLMs (figures not read) | MIT [P] |
| **EEBench** V1 ([blog](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)) | 13 tasks in atopile; real parts with tolerances | SPICE corners + design and cost checks | Claude Opus 5 61.6% (top), 2026-09-01; → [pcb-llm-benchmarks](../llm/pcb-llm-benchmarks.md) | [P] |
| **Schemato** ([2411.13899](https://arxiv.org/abs/2411.13899)) vs **Weave** ([2607.03835](https://arxiv.org/abs/2607.03835)) | Netlist → LTspice `.asc`: LLM vs deterministic layered layout | Weave re-parses output, compares net for net (equivalence certificate) | Schemato 76% compile. Weave 100% on 117 circuits; 88.4% of 3,460 ADI demo circuits, failing on dense power modules | Weave licence not stated [P] |
| **EEschematic** ([2510.17002](https://arxiv.org/abs/2510.17002)) | SPICE netlist → drawn schematic, multimodal LLM, visual chain of thought | — | 3 analog examples, no metrics [P] | — |
| **MultModLM** ([2606.27666](https://arxiv.org/abs/2606.27666)) | RTL → schematic, 99 modules | Rubric, LLM judges, humans | LLM judges: "near-zero agreement" with human raters [P] | — |
| **AnalogCoder** ([2405.14918](https://arxiv.org/abs/2405.14918)) | Analog design as Python (PySpice [S]) with verified subcircuit library | Simulation feedback | 20 circuits designed vs 15 for GPT-4o [P] | — |
| Image → netlist: Masala-CHAI ([2411.14299](https://arxiv.org/abs/2411.14299)), SINA ([2601.22114](https://arxiv.org/html/2601.22114v1)), Netlistify (NVIDIA, MLCAD 2025) | Schematic image → SPICE netlist | — | SINA 96.5% vs Masala-CHAI 35.5% on 40 images [S] | — |

1. **Grounding.** PCBSchemaGen pass falls 81.3% → 26.8% without the datasheet KG [P].
2. **Pin-level feedback.** Verifier reporting pass/fail instead of pin-level errors: 57.7% (≈+24 points for pin-level) [P]. Give the LLM pin-level findings from every checker, never pass/fail [I].
3. **ERC-clean is a low bar.** ERC alone accepts 10–13 points more PCBSchemaGen candidates than the full verifier (→ [ERC row](part-selection-and-verification.md#schematic-verification-beyond-erc-q3)) [P].
4. **Open part choice is poor:** 4.4–8.2% fully correct on HWE-Bench vs 94% on PCBBench (ICs and KG given) [P].
5. Reuse PCBSchemaGen's verifier design (MIT) and PCBBench/OSE as regression fixtures; they need SKiDL output, which we can emit [I].
6. Grade readability with symbol/label overlap counts (SchGen's metric), sheet size and labels per net; not with LLM judges (MultModLM) [I].

## Field evidence: one prompt, nine tools

[devbisme/ai-circuit-design-tests](https://github.com/devbisme/ai-circuit-design-tests): same dual-ADC USB prompt to each tool, Opus 5.5 [P].

1. Every run reached a routed 4-layer board; all but one had 0 DRC errors (one had 4). Cost $10.87–$61.12.
2. Fine-grained MCP editing (one item per call): ≈3× the tokens of script-driven runs. Avoid per-edit MCP tools [I].
3. Baseline, Claude with no KiCad tools (SKiDL, schematizer, own pcbnew scripts): $11.16; ERC 0 errors, 435 warnings.
4. Parity caught writer bugs: comparing the `kicad-cli` netlist of the drawn schematic with the SKiDL netlist caught a schematizer bug that drew a resistor over a capacitor and shorted +1V2 to GND. In another run SKiDL's generator merged GND and +3V3 (910 violations); Claude wrote a label-based writer instead.
5. boardforge: every routed board came from single-file netlist → label-based writer → `kicad-cli` parity → scripted placement → Freerouting. "ERC and DRC passing is a weak measure of quality" ([design.md](https://github.com/devbisme/boardforge/blob/master/docsrc/design.md)).
6. skidl-skills made netlists byte-stable across regenerations; otherwise "update PCB from schematic" discards placement.
7. Readability: "really huge/unreadable single page schematics" after ordering ≈15 AI-designed boards ([llm-field-reports](../workflow/llm-field-reports.md)) [P]. No study measures human review of labels-only vs wired generated schematics [I].

## KiCad 9/10 schematic pitfalls (Q5)

| Topic | Fact | Source |
|---|---|---|
| Version | `SEXPR_SCHEMATIC_FILE_VERSION`: **9.0 = 20250114, 10.0 = 20260306**, master (11) = 20261015. Symbol libraries: 9.0 = 20241209, 10.0 = 20251024. 10.0 adds local power symbols (20250227), custom body styles, stacked pins, variants, flat hierarchy | [sch_file_versions.h](https://gitlab.com/kicad/code/kicad/-/blob/10.0/eeschema/sch_file_versions.h) [P] |
| Header | `generator` must not be `eeschema` for third-party writers; `generator_version` since 20231120 | [dev-docs](https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/index.html) [P] |
| `lib_symbols` | Embed every symbol used (why schematizer needs no library access). Embedded copies differing from the installed library raise ERC library-mismatch warnings (155 in one run) | schematizer README; null-test run [P] |
| Instances | Every symbol has ≥1 `instances` entry: `(project NAME (path "/<root-uuid>/…" (reference R1) (unit 1)))`; first path element = root sheet UUID. Wrong project name or UUIDs → references show `?` (SKiDL 2.3.0 fix) | dev-docs; SKiDL history [P] |
| UUIDs | Footprints link to symbols **by UUID**, not refdes; a deleted and recreated symbol gets a new footprint unless "re-link by reference designator" is used. Derive UUIDs deterministically (UUIDv5 of the IR path) | [pcbnew manual 10.0](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html) [P]; UUIDv5 [I] |
| Geometry | Symbol space Y-up, schematic space Y-down; 1.27 mm grid; pin positions need symbol rotation and mirror (kicad-sch-api ignores rotation); only wire **ends** connect, crossings do not | [kicad-sch-api](https://github.com/circuit-synth/kicad-sch-api); [eeschema manual](https://docs.kicad.org/10.0/en/eeschema/eeschema.html) [P] |
| Net names | Priority: global label > power symbol > local label > hierarchical label > sheet pin; ties alphabetical | eeschema manual [P] |
| Power | Power symbols are global; local power symbols in 10.0. Ground and passive-fed rails need **PWR_FLAG**; power does not "jump" across a passive filter. Hidden power pins create implicit connections | eeschema manual [P] |
| Labels | Labels-only writers must deconflict overlapping labels, orient labels away from pins, emit real power symbols not `??` (all SKiDL 2.3.0 fixes). Multi-unit parts share one base reference | SKiDL history [P] |
| Round trips | kicad-sch-api dropped every pin UUID on load+save (403-line diff). Regenerate; never round-trip through a lossy parser | [ROUNDTRIP_FIDELITY_ISSUES.md](https://github.com/circuit-synth/kicad-sch-api/blob/main/docs/ROUNDTRIP_FIDELITY_ISSUES.md) [P] |
| Libraries | KiCad 10 libraries can be `.kicad_symdir` (one file per symbol). In master, generic `Q_NMOS` numbers pins `D/G/S` and depends on new pin-to-pad maps (symbol library version 20260629); writers assuming numeric pins need an update for KiCad 11 | SKiDL 3.0.0 history; [kicad-symbols](https://gitlab.com/kicad/libraries/kicad-symbols) [P] |
| Validators | `kicad-cli sch erc --format json --severity-all --exit-code-violations` (exit 5 on violations). `kicad-cli sch export netlist --format kicadsexpr` (also kicadxml, spice). Netlists omit `#` references (power symbols, PWR_FLAG): compare without them | [CLI 10.0](https://docs.kicad.org/10.0/en/cli/cli.html); schematizer README [P] |
| Schematic → board | 10.x has no headless "Update PCB from Schematic"; field runs built the board from the netlist in pcbnew Python; one MCP needed xdotool. KiCad 11 IPC API adds netlist import ([ipc-api-10-vs-11](../kicad/ipc-api-10-vs-11.md)) | boardforge design.md [P] |

## Writer and parity-gate design

[I], from the facts above:
1. **One writer interface** (schematizer first, our own if needed) providing: the harness-pinned format (10.0 = `20260306`, or `20250114` if 9.x users must open files); `lib_symbols` from a **pinned** KiCad library version; deterministic UUIDs and refdes; explicit no-connect flags; a PWR_FLAG insertion rule; project-name binding.
2. **Parity gate, mandatory for any writer:** export the `kicad-cli` netlist, compare with the IR pin by pin, ignoring `#` references. Triage ERC JSON against an explicit expected-warning list; every other ERC item blocks.
3. **Board from netlist** in pcbnew Python on 10.x; switch to KiCad 11 IPC netlist import when it ships. Carry block, class and intent data across (→ [placement intent](part-selection-and-verification.md#placement-intent-at-schematic-time-q4)).
4. Never let the LLM author `.kicad_sch` text or schematic coordinates; never commit unseeded random layouts; never treat ERC-clean as done.

## Open questions

- Benchmarks disagree by 10×: PCBBench 94% vs HWE-Bench 5–8%. Our product ("solar MPPT charger") resembles HWE-Bench; expect the low number without grounding [I].
- Labels-only is exact but may be hard to review; no evidence says which form reviewers check more accurately.
- schematizer has two releases and already shipped a short-circuit bug. pcbGPT's and SchGen's code availability is unclear.
- atopile public `main` lags PyPI by six months; picker endpoint list (R, C, L only) confirmed in the 0.15.9 wheel.

## Sources

- research notes: none; new research 2026-10-23. Earlier coverage: [read-representations](../llm/read-representations.md), [pcb-llm-benchmarks](../llm/pcb-llm-benchmarks.md). Primary sources are linked inline.
- also read: [PCBSchemaGen abs](https://arxiv.org/abs/2602.00510), [SINA abs](https://arxiv.org/abs/2601.22114), [schematizer](https://github.com/devbisme/schematizer), [circuit-json-to-kicad](https://github.com/tscircuit/circuit-json-to-kicad), [circuit-synth](https://github.com/circuit-synth/circuit-synth), [atopile-easyeda2kicad on PyPI](https://pypi.org/project/atopile-easyeda2kicad/); other paper abs pages: [pcbGPT](https://arxiv.org/abs/2606.01188), [SchGen](https://arxiv.org/abs/2605.30345), [HWE-Bench](https://arxiv.org/abs/2603.18102).
- see also: [constraint-ir](../architecture/constraint-ir.md), [interfaces-relations-vs-coordinates](../llm/interfaces-relations-vs-coordinates.md), [kicad-cli](../kicad/kicad-cli.md), [file-format-and-version-hazards](../kicad/file-format-and-version-hazards.md), [field-failure-modes](../ux/field-failure-modes.md).
