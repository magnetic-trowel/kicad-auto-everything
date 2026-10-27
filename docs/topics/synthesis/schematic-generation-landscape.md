# Schematic generation: prior art and KiCad output

**TL;DR**
- Every open system that gets as far as a board has the LLM write **code or a typed IR**; a deterministic writer then emits KiCad. On the same model, anchor-relative, pin-name code gave 82.0% valid schematics against 32.5% for raw `.kicad_sch` [P]. Our typed-IR plan is the right shape.
- **Grounding and pin-level feedback are the biggest levers.** PCBSchemaGen falls from 81.3% to 26.8% pass without its datasheet knowledge graph, and to 57.7% when the verifier reports pass/fail instead of pin-level errors [P]. Open-ended board design, where the model chooses the parts, is still poor: 4.4–8.2% of designs fully correct on HWE-Bench [P].
- **ERC-clean is a low bar.** In a nine-tool field comparison, every routed board passed ERC and still carried spec-level faults. In PCBSchemaGen, ERC alone accepts 10–13 points more candidates than the full verifier [P].
- **Readable or exact.** Writers either auto-place symbols and draw wires (schematizer, tscircuit, JITX, Weave) or write labels only, which is exact by construction. Wire-drawing writers have shipped shorts (schematizer joined +1V2 to GND), so a **`kicad-cli` netlist parity gate** is mandatory whichever we choose [P].
- **KiCad pitfalls that bite generators:**
  - the version token (9.0 = `20250114`, 10.0 = `20260306`);
  - embedded `lib_symbols`;
  - per-symbol `instances` keyed by project name and root UUID;
  - **stable UUIDs**, because footprints link to symbols by UUID;
  - PWR_FLAG on passive-fed rails, and explicit no-connect flags [P].

## Key facts

Tags: [P] primary (paper, docs or source code read); [S] snippet/secondary; [V] vendor claim; [I] inference. Repositories were read as of 2026-10-22.

### Code-first tools and commercial generators

| Tool | Representation | Parts: chosen and checked | Correctness checks | Output and readability | Licence; activity |
|---|---|---|---|---|---|
| **SKiDL** 3.0.0 | Python netlist DSL: parts, pins by name or alias, nets, buses, subcircuits, part and net classes | KiCad symbols; `skidl-part-search` (SQLite index). No MPN or stock check | Built-in ERC with pin types and drive strength; SPICE via PySpice | Netlist, PCB, SPICE. Schematics (KiCad 6–10) are delegated to **schematizer** since 3.0.0 | MIT; released 2026-10-16 ([history](https://github.com/devbisme/skidl/blob/master/HISTORY.md)) [P] |
| **schematizer** 0.2.0 | Generic hierarchical JSON netlist with embedded symbol graphics | — | None of its own | `.kicad_sch` or SVG. Default mode places and routes, **randomly on each run, with no seed**. `labels` mode: grid placement, a stub plus power symbol or label on every pin, one sheet per subcircuit, about 2 s for 190 parts | MIT; first released 2026 ([PyPI](https://pypi.org/project/schematizer/)) [P] |
| **atopile** | Declarative `ato`: modules, typed interfaces, units, tolerances, `assert` constraints; set-valued parameter solver | Parametric picking **only for R, C, L**, from a hosted API (`components.atopileapi.com`), within the solved bounds. Other parts come in by LCSC ID through `atopile-easyeda2kicad` | Design checks (`requires_pulls`; power-bus voltage aliasing; current summing); constraint consistency | **`.kicad_pcb` only**, no `.kicad_sch` (graph viewer). Sub-module layouts are reused as groups | MIT, but the required `atopile-easyeda2kicad` is **AGPL-3.0**. PyPI 0.15.9 (2026-09-12); public `main` last commit 2026-03-11 ([repo](https://github.com/atopile/atopile)) [P] |
| **tscircuit** | React/TSX elements → Circuit JSON | JLCPCB parts via the community jlcsearch API [S] | Source DRC checks; SPICE and IBIS simulation elements | Own schematic, PCB and autorouter. Schematic layout modes include `match-adapt` (matches the graph against a corpus of drawn layouts), grid, flex and matchpack, plus a trace solver and net labels. `circuit-json-to-kicad` writes format `20250114` | MIT; near-daily releases (0.0.3006 on 2026-10-22) ([core](https://github.com/tscircuit/core)) [P] |
| **Diode Zener / `pcb`** | Starlark DSL; typed nets (`Power`, `Ground`); modules; interfaces | KiCad symbol libraries; package registry | `TestBench` checks with circuit-path and component-sequence matchers | KiCad 10 layout. Schematic preview, with placement persisted in comment blocks | MIT ([repo](https://github.com/diodeinc/pcb)) [P]. In blind comparisons of generated reference designs, Diode engineers preferred Sonnet 4.5 over Opus 4 (60:40) and over Sonnet 4 (82:18). Testbenches grade requirements, e.g. "≥22 µF between power and ground", not exact parts ([Anthropic](https://claude.com/blog/making-claude-a-better-electrical-engineer)) [V] |
| **circuit-synth** + **kicad-sch-api** | Python `@circuit` functions | KiCad library search; JLCPCB lookups via Claude Code agents | KiCad ERC | `.kicad_sch` with **a net label on every pin** plus hierarchical labels. kicad-sch-api targets KiCad 7/8 | MIT; releases 0.12.1 (2026-01-09) and 0.5.6 (2025-11-19). Slowing [P] |
| **JITX** (Python 4.x) | Python API (Stanza before 4.0) | `jitxlib.parts` query API [V] | Design constraints [V] | Auto-drawn schematic: wires inside a `SchematicGroup`, **net labels where wires cross groups**. Connectivity can't be edited in the GUI ([docs](https://docs.jitx.com/en/4.0/api/jitx.circuit.html)) [P] | Proprietary |
| **Flux** | Browser EDA plus agent | Own library, price and stock, datasheet reading [V] | AI review, FMEA, DRC [V] | Places and wires parts in its own format ([docs](https://docs.flux.ai/reference/copilot.md)) | Proprietary; no accuracy claims |
| **CELUS** | Requirements → CUBO function blocks | Curated CUBO catalog with lifecycle data | Not published | Schematic plus BOM; KiCad export with a library package; no layout ([KiCad export](https://www.celus.io/blog/kicad-libraries-exportpackage)) [V] | Proprietary |
| **Circuit Mind** ACE | Requirements → variables and constraints → solver ([US 12,050,847 B2](https://patents.google.com/patent/US12050847)) [P] | Own database | "Independent rule checks"; claims error-free output [V] | Schematic plus BOM [V] | Proprietary |
| **boardforge** / **skidl-skills** | Multi-agent Claude Code pipeline that writes SKiDL | pcbparts MCP (JLCPCB parametric search, Mouser/DigiKey stock); `kipart` symbols from datasheet pin tables | Independent ERC-reviewer agent; `kicad-cli` parity; ngspice review gate | schematizer `labels` mode → parity → pcbnew placement → Freerouting | MIT ([boardforge](https://github.com/devbisme/boardforge), [skidl-skills](https://github.com/devbisme/skidl-skills)) [P] |

Quilter and DeepPCB consume an existing schematic and board; neither generates schematics ([../landscape/quilter.md](../landscape/quilter.md), [../landscape/deeppcb.md](../landscape/deeppcb.md)). Cadstrom ("Sigma Engine", $6.8M seed) and AllSpice DRCY review designs rather than generate them [S]/[V]. Commercial context: [../landscape/commercial-incumbents-and-startups.md](../landscape/commercial-incumbents-and-startups.md).

### Papers and benchmarks, 2024–2026

| Work | Task and representation | Correctness check | Result | Code |
|---|---|---|---|---|
| **PCBSchemaGen** ([2602.00510](https://arxiv.org/html/2602.00510v2), v2 Jun 2026) | Spec plus required ICs → SKiDL. Per-IC knowledge graph from datasheets: a 32-role pin ontology, 4 predicate templates (`supply_pair`, `must_be_connected`, `driving_pair`, `diff_pair_distinct`), about 300 tokens per IC, 47 ICs | 5-layer verifier: ERC; pin-role net matching; subcategory templates; VF2 topology signatures; power invariants. Errors are localized to pins. κ = 0.91 against senior engineers; 6.7% false accept | Pass@1 (4 calls) on PCBBench (62 tasks): GPT-5.4 94.0, Gemini 3.1 Pro 94.3, Gemma-4-31B 81.3. On the held-out OSE set (165 tasks): GPT-5.4 79.3, Gemma 69.8. A Circuitron-style prompting baseline: 41.9 / 20.7 | MIT ([repo](https://github.com/HZou9/PCBSchemaGen_v2)) [P] |
| **pcbGPT** ([2606.01188](https://arxiv.org/html/2606.01188), KIT/Bosch) | Chat → Python DSL. An invalid pin name returns the list of valid pins; `FlexiblePin` covers interchangeable pins → KiCad project | Execute, then ERC, then a separate LLM validator against datasheet summaries | 20 tasks: GPT-5.3-Codex pass@1 0.90 (hard tier 0.72); GPT-5.1 0.60 (hard 0.12). Failure rate correlates with component count (r = 0.863) | Not stated [P] |
| **SchGen** ([2605.30345](https://arxiv.org/html/2605.30345v1)) | NL → schematic code with anchor-relative placement and pin-name wiring; fine-tuned GPT-oss-20B | Code runs and KiCad ERC finds zero critical errors; netlist Jaccard; 2 experts | 82.0% valid / 60.5% functional, against 32.5% / 3.0% for raw KiCad text. GPT-5.2: 50.0% functional | — [P]; detail in [../llm/read-representations.md](../llm/read-representations.md) |
| **HWE-Bench** ([2603.18102](https://arxiv.org/html/2603.18102)) | Requirements plus 2,914 datasheets → board netlist; **the model selects the parts**; 300 tasks | Static pin and protocol checks, then an LTspice transient against a ground-truth testbench | Fully correct: Claude Sonnet 4.5 8.15%, GPT-5.2 6.58%, Gemini 3.1 Pro 5.16%, Grok-4 4.40% | [P] |
| **CircuitLM** ([2601.04505](https://arxiv.org/abs/2601.04505), ICLAD 2026) | NL → CircuitJSON, grounded in a curated component KB with canonical pinouts | Deterministic ERC with severity classes, plus an LLM judge | 100 prompts × 5 LLMs (figures not read) | MIT [P] |
| **EEBench** V1 ([blog](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)) | 13 tasks in atopile; real parts with tolerances | SPICE corners plus design and cost checks | Claude Opus 5 61.6% (top), 2026-09-01 | See [../llm/pcb-llm-benchmarks.md](../llm/pcb-llm-benchmarks.md) [P] |
| **Schemato** ([2411.13899](https://arxiv.org/abs/2411.13899)) vs **Weave** ([2607.03835](https://arxiv.org/abs/2607.03835)) | Netlist → LTspice `.asc` (LLM vs deterministic layered layout) | Weave re-parses its output and compares it net for net, as an equivalence certificate | Schemato 76% compile. Weave 100% on 117 circuits; 88.4% of 3,460 ADI demo circuits, with failures in dense power modules | Weave licence not stated [P] |
| **EEschematic** ([2510.17002](https://arxiv.org/abs/2510.17002)) | SPICE netlist → drawn schematic by a multimodal LLM with visual chain of thought | — | 3 analog examples, no metrics [P] | — |
| **MultModLM** ([2606.27666](https://arxiv.org/abs/2606.27666)) | RTL → schematic, 99 modules | Rubric, LLM judges, humans | LLM judges show "near-zero agreement" with human raters [P] | — |
| **AnalogCoder** ([2405.14918](https://arxiv.org/abs/2405.14918)) | Analog design as Python (PySpice [S]) code, with a library of verified subcircuits | Simulation feedback | 20 circuits designed, vs 15 for GPT-4o [P] | — |
| Image → netlist: Masala-CHAI ([2411.14299](https://arxiv.org/abs/2411.14299)), SINA ([2601.22114](https://arxiv.org/html/2601.22114v1)), Netlistify (NVIDIA, MLCAD 2025) | Schematic image → SPICE netlist | — | SINA 96.5% vs Masala-CHAI 35.5% on 40 images [S] | — |

### Field evidence: one prompt, nine tools

[devbisme/ai-circuit-design-tests](https://github.com/devbisme/ai-circuit-design-tests) gave each tool the same dual-ADC USB prompt (Opus 5.5) [P]:
- **Outcome.** Every run reached a routed 4-layer board. All but one had 0 DRC errors (that one had 4). Costs ranged from $10.87 to $61.12. Fine-grained MCP editing (one item per call) used about 3× the tokens of script-driven runs.
- **Baseline.** Claude with no KiCad tools (SKiDL, schematizer, its own pcbnew scripts) cost $11.16. ERC gave 0 errors and 435 warnings.
- **Parity catches writer bugs.**
  - The baseline compared the `kicad-cli` netlist of the drawn schematic with the SKiDL netlist. That caught a schematizer bug that drew a resistor over a capacitor and shorted +1V2 to GND.
  - In another run, SKiDL's generator merged GND and +3V3 (910 violations), so Claude wrote a label-based writer instead.
- **boardforge's summary.**
  - Every routed board came from one pattern: single-file netlist → label-based schematic writer → `kicad-cli` parity → scripted placement → Freerouting.
  - "ERC and DRC passing is a weak measure of quality" ([design.md](https://github.com/devbisme/boardforge/blob/master/docsrc/design.md)).
- **Byte-stable output matters.** skidl-skills made its netlists byte-stable across regenerations; without that, "update PCB from schematic" discards placement.

Readability complaints: "really huge/unreadable single page schematics" after ordering about 15 AI-designed boards ([../workflow/llm-field-reports.md](../workflow/llm-field-reports.md)) [P]. No study measures how well humans review labels-only versus wired generated schematics [I].

### KiCad 9/10 schematic pitfalls (Q5)

| Topic | Fact | Source |
|---|---|---|
| Version | `SEXPR_SCHEMATIC_FILE_VERSION`: **9.0 = 20250114, 10.0 = 20260306**, master (11) = 20261015. Symbol libraries: 9.0 = 20241209, 10.0 = 20251024. 10.0 adds local power symbols (20250227), custom body styles, stacked pins, variants and flat hierarchy | [sch_file_versions.h](https://gitlab.com/kicad/code/kicad/-/blob/10.0/eeschema/sch_file_versions.h) [P] |
| Header | `generator` must not be `eeschema` for third-party writers; `generator_version` exists since 20231120 | [dev-docs](https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/index.html) [P] |
| `lib_symbols` | Embed every symbol used. schematizer needs no library access for this reason. Embedded copies that differ from the installed library raise ERC library-mismatch warnings (155 in one run) | schematizer README; null-test run [P] |
| Instances | Every symbol has at least one `instances` entry: `(project NAME (path "/<root-uuid>/…" (reference R1) (unit 1)))`. The first path element is the root sheet's UUID. If the project name or UUIDs are wrong, references show as `?` (SKiDL 2.3.0 fix) | dev-docs; SKiDL history [P] |
| UUIDs | Footprints link to symbols **by UUID**, not refdes. A deleted and recreated symbol gets a new footprint unless "re-link by reference designator" is used. Derive UUIDs deterministically, e.g. UUIDv5 of the IR path | [pcbnew manual 10.0](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html) [P]; UUIDv5 [I] |
| Geometry | Symbol space is Y-up and schematic space Y-down. Use the 1.27 mm grid. Pin positions need the symbol's rotation and mirror (kicad-sch-api ignores rotation). Only wire **ends** connect; crossing wires do not | [kicad-sch-api](https://github.com/circuit-synth/kicad-sch-api); [eeschema manual](https://docs.kicad.org/10.0/en/eeschema/eeschema.html) [P] |
| Net names | Priority: global label > power symbol > local label > hierarchical label > sheet pin; ties go alphabetically | eeschema manual [P] |
| Power | Power symbols are global; local power symbols arrive in 10.0. Ground and passive-fed rails need **PWR_FLAG**, and power does not "jump" across a passive filter. Hidden power pins create implicit connections | eeschema manual [P] |
| Labels | Labels-only writers must deconflict overlapping labels, orient labels away from pins, and emit real power symbols, not `??` (all SKiDL 2.3.0 fixes). Multi-unit parts share one base reference | SKiDL history [P] |
| Round trips | kicad-sch-api dropped every pin UUID on load and save (403-line diff). Regenerate rather than round-trip through a lossy parser | [ROUNDTRIP_FIDELITY_ISSUES.md](https://github.com/circuit-synth/kicad-sch-api/blob/main/docs/ROUNDTRIP_FIDELITY_ISSUES.md) [P] |
| Libraries | KiCad 10 libraries can be `.kicad_symdir` (one file per symbol). In master, generic `Q_NMOS` numbers its pins `D/G/S` and depends on new pin-to-pad maps (symbol library version 20260629) | SKiDL 3.0.0 history; [kicad-symbols](https://gitlab.com/kicad/libraries/kicad-symbols) [P] |
| Validators | `kicad-cli sch erc --format json --severity-all --exit-code-violations` (exit code 5 on violations). `kicad-cli sch export netlist --format kicadsexpr` (also kicadxml, spice). Netlists omit `#` references (power symbols, PWR_FLAG), so compare without them | [CLI 10.0](https://docs.kicad.org/10.0/en/cli/cli.html); schematizer README [P] |
| Schematic → board | 10.x has no headless "Update PCB from Schematic". Field runs built the board from the netlist in pcbnew Python; one MCP needed xdotool. KiCad 11's IPC API adds netlist import ([../kicad/ipc-api-10-vs-11.md](../kicad/ipc-api-10-vs-11.md)) | boardforge design.md [P] |

## Recommendations for our system

**Reuse** [I]:
1. **schematizer** (MIT) as the first `.kicad_sch` backend. Emit its generic JSON netlist from our IR and run its `labels` mode, with one sheet per functional block. Pretty layouts are a later, optional view.
2. **PCBSchemaGen's verifier design** (MIT): the pin-role ontology, predicate templates, VF2 topology signatures, pin-level error messages and graded reward. Use PCBBench and OSE as regression fixtures; they need SKiDL output, which we can emit.
3. **kicad-happy** (MIT) as an independent second-opinion analyser of the emitted `.kicad_sch` (see [part-selection-and-verification.md](part-selection-and-verification.md)).
4. **Ideas, not packages**, from:
   - atopile: set-valued parameters with tolerances; bus parameters that alias voltage and sum current; `requires_pulls`;
   - Diode: topology test benches;
   - Weave: equivalence certificates;
   - pcbGPT: an invalid pin returns the valid pin list.

**Build** [I]:
1. **A KiCad writer behind one interface** (schematizer first, our own if needed). It must provide:
   - the format of the KiCad version the harness pins (10.0 = `20260306`), or `20250114` if 9.x users must open the files;
   - `lib_symbols` embedded from a **pinned** KiCad library version;
   - deterministic UUIDs and refdes;
   - explicit no-connect flags;
   - a PWR_FLAG insertion rule;
   - project-name binding.
2. **A parity gate.** Export the `kicad-cli` netlist and compare it with the IR pin by pin, ignoring `#` references. Triage ERC JSON with an explicit list of expected warnings; every other ERC item blocks.
3. **Board from netlist** in pcbnew Python on 10.x, switching to the KiCad 11 IPC netlist import when it ships. Carry block, class and intent data across (see the placement section of the companion doc).
4. **Pin-level feedback** to the LLM from every checker, not pass/fail; PCBSchemaGen measured this at +24 points.
5. **Readability checks:** symbol/label overlap counts (SchGen's metric), sheet size, and labels per net. Do not grade readability with LLM judges (MultModLM).

**Avoid** [I]:
- LLM-authored `.kicad_sch` text or schematic coordinates.
- Fine-grained per-edit MCP tools (about 3× the tokens).
- Unseeded random layouts in version control.
- Lossy parse-and-save round trips.
- Shipping atopile as a dependency: its required LCSC importer is AGPL-3.0, and its picker needs a hosted API key. See [../licensing/reuse-matrix.md](../licensing/reuse-matrix.md).
- Treating ERC-clean as done.

## Conflicts and open questions

- **Benchmarks disagree by 10×.** PCBBench (ICs given, KG supplied) reaches 94%; HWE-Bench (open part selection plus simulation) 5–8%. Our product ("solar MPPT charger") resembles HWE-Bench, so expect the low number without grounding [I].
- **Exact or readable.** Labels-only output is exact but may be hard to review. No evidence says which one reviewers check more accurately.
- **Writer maturity.** schematizer has two releases and has already shipped a short-circuit bug. pcbGPT's and SchGen's code availability is unclear.
- **KiCad 11 change.** Pin-to-pad maps will change how generic symbols bind to footprints. Writers that assume numeric pins will need an update.
- **atopile status.** Its public `main` lags PyPI by six months. The picker endpoint list (R, C, L only) was confirmed in the 0.15.9 wheel.

## Sources

- research notes: none; this is new research (2026-10-23). Earlier coverage: [../llm/read-representations.md](../llm/read-representations.md), [../llm/pcb-llm-benchmarks.md](../llm/pcb-llm-benchmarks.md).
- papers: [PCBSchemaGen](https://arxiv.org/abs/2602.00510), [pcbGPT](https://arxiv.org/abs/2606.01188), [SchGen](https://arxiv.org/abs/2605.30345), [HWE-Bench](https://arxiv.org/abs/2603.18102), [CircuitLM](https://arxiv.org/abs/2601.04505), [Weave](https://arxiv.org/abs/2607.03835), [Schemato](https://arxiv.org/abs/2411.13899), [EEschematic](https://arxiv.org/abs/2510.17002), [MultModLM](https://arxiv.org/abs/2606.27666), [AnalogCoder](https://arxiv.org/abs/2405.14918), [Masala-CHAI](https://arxiv.org/abs/2411.14299), [SINA](https://arxiv.org/abs/2601.22114).
- code: [SKiDL](https://github.com/devbisme/skidl), [schematizer](https://github.com/devbisme/schematizer), [atopile](https://github.com/atopile/atopile), [tscircuit core](https://github.com/tscircuit/core), [circuit-json-to-kicad](https://github.com/tscircuit/circuit-json-to-kicad), [Diode pcb](https://github.com/diodeinc/pcb), [circuit-synth](https://github.com/circuit-synth/circuit-synth), [kicad-sch-api](https://github.com/circuit-synth/kicad-sch-api), [boardforge](https://github.com/devbisme/boardforge), [ai-circuit-design-tests](https://github.com/devbisme/ai-circuit-design-tests), [atopile-easyeda2kicad on PyPI](https://pypi.org/project/atopile-easyeda2kicad/).
- KiCad: [schematic format](https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/index.html), [file versions](https://gitlab.com/kicad/code/kicad/-/blob/10.0/eeschema/sch_file_versions.h), [eeschema 10.0](https://docs.kicad.org/10.0/en/eeschema/eeschema.html), [CLI 10.0](https://docs.kicad.org/10.0/en/cli/cli.html).
- vendors: [Flux agent](https://docs.flux.ai/reference/copilot.md), [JITX circuit API](https://docs.jitx.com/en/4.0/api/jitx.circuit.html), [CELUS](https://www.celus.io/blog/kicad-libraries-exportpackage), [Circuit Mind patent](https://patents.google.com/patent/US12050847), [Anthropic + Diode](https://claude.com/blog/making-claude-a-better-electrical-engineer).

See also: [part-selection-and-verification.md](part-selection-and-verification.md), [../architecture/constraint-ir.md](../architecture/constraint-ir.md), [../llm/interfaces-relations-vs-coordinates.md](../llm/interfaces-relations-vs-coordinates.md), [../kicad/kicad-cli.md](../kicad/kicad-cli.md), [../kicad/file-format-and-version-hazards.md](../kicad/file-format-and-version-hazards.md), [../ux/field-failure-modes.md](../ux/field-failure-modes.md)
