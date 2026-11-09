# Part selection, schematic verification and placement intent

Scope: where part data comes from, how to keep MPNs and pinouts real, reported failure rates, checks beyond ERC, and how schematic-time placement intent reaches layout. Not here: schematic generators, papers, KiCad writer pitfalls -> [schematic-generation-landscape.md](schematic-generation-landscape.md).
Keys: part selection, MPN, catalog-first, part card, pinout, three-way pin check, DigiKey API, Mouser API, Nexar, Octopart, element14, JLCPCB, LCSC, jlcparts, pcbparts MCP, EasyEDA, easyeda2kicad, lifecycle, NRND, package hallucination, kicad-happy, pin-role predicates, ERC, derating, MLCC DC bias, ngspice, PySpice, InSpice, spicelib, reviewer LLM, DRCY, placement intent, Component Class, placement rule areas, Repeat Layout, design blocks, rooms, `pcb-intent`

Tags: [P] primary; [S] snippet/secondary; [V] vendor; [I] inference. Research done 2026-10-23.

## Part data sources (Q2)

| Source | What it gives | Limits and terms |
|---|---|---|
| KiCad libraries | Symbols, footprints, 3D models. Generic symbols encode pin order in names (`D_Dual_CommonAnode_AKK`, `Q_NJFET_GSD`); master `Q_NMOS` pin-to-pad maps → [Libraries row](schematic-generation-landscape.md#kicad-910-schematic-pitfalls-q5) [P] | CC-BY-SA 4.0, article 3 waived for designs using them ([licence](https://www.kicad.org/libraries/license/)). No MPN, stock or lifecycle data [P] |
| DigiKey Product Information v4 | Keyword and parametric search; `ProductStatus` (Active, Active Not Stocked, Discontinued, Last Time Buy, Not For New Designs, Obsolete; values as parsed by kicad-happy); substitutions; datasheet URL | OAuth; 120 requests/min and 1,000/day by default ([docs](https://developer.digikey.com/documentation)) [P] |
| Mouser Search API | MPN and keyword search; lifecycle (New Product, End of Life, …) | 30 calls/min free tier [S] |
| Nexar / Octopart | Aggregated offers, specs, lifecycle, datasheets | Evaluation: 100 matched parts with lifecycle, specs, datasheets. Standard: 2,000 parts without them. Pro: 15,000, with them as add-ons ([plans](https://nexar.com/compare-plans)) [P] |
| element14 | Specs, datasheets | 2 calls/s and 1,000/day "courtesy" allowance [S] |
| JLCPCB / LCSC | Stock, basic/extended status, price, package | Official API needs approval [S]. Community jlcparts SQLite dump ≈11 GB [S]. jlcsearch dropped manufacturer and datasheet fields in 2026-09 ([part-layout-card](../llm/part-layout-card.md)) [P] |
| pcbparts MCP | Parametric search over 630k+ in-stock JLCPCB parts; live Mouser/DigiKey stock; footprints via SamacSys; pinouts from EasyEDA symbols; ≈285 OSHW reference boards | MIT code, hosted service; third-party data terms not checked ([repo](https://github.com/Averyy/pcbparts-mcp)) [P]/[V] |
| EasyEDA/LCSC symbols | Symbol + footprint per LCSC part | Common importer easyeda2kicad is AGPL-3.0 [P]; contributed data of unknown accuracy [I] |

- Put adapters for DigiKey, Mouser, Nexar and LCSC behind one interface, with caching for rate limits and schema churn. Use LCSC/EasyEDA data, not the AGPL importer code [I].
- Per-part layout data: [part-layout-card](../llm/part-layout-card.md); extraction methods: [datasheet-extraction](../llm/datasheet-extraction.md).

## How tools keep parts real and pinouts right

| Tool | Mechanism | Gap |
|---|---|---|
| pcbGPT | Searches only installed KiCad libraries (embedding + lexical). Invalid pin name → returns valid pin list. Footprints validated at creation. Failed datasheet extraction → part reported "unavailable", agent picks another [P] | No stock or lifecycle check |
| atopile | Parametric pick from a parts database within solver bounds; picked part's attributes attached back as constraints [P] | R, C, L only; other parts take EasyEDA pinouts |
| PCBSchemaGen | Per-IC KG induced from the datasheet: pin table → pin roles → predicates [P] | Task supplies the ICs; 47-IC library |
| CircuitLM | Curated component KB with canonical pinouts [P] | KB scale unknown |
| skidl-skills | Sourcing agent (pcbparts); datasheet librarian; `kipart` symbols from datasheet pin tables, pin counts checked [P] | Footprint check only confirms the file exists. When datasheet downloads failed (FTDI 403s), pins were written from memory |
| AllSpice DRCY | Agentic datasheet retrieval; critic weights pin-function coverage at 40%; k-run consensus ([datasheet-extraction](../llm/datasheet-extraction.md)) [P] | No published accuracy |
| Siemens Xpedition schematic analysis (ex-Valydate) | Builds models from the BOM MPN, not the symbol ([blog](https://blogs.sw.siemens.com/electronic-systems-design/2017/11/04/a-brief-introduction-to-schematic-integrity-analysis/)) [V] | Proprietary; rule list unpublished |

Rules [I]:
1. **Catalog-first.** Part identity is a lookup, never generated text: retrieve candidates by parametric query (KiCad libraries for symbols/footprints; JLCPCB/LCSC, DigiKey/Mouser for stock, lifecycle, price); the LLM picks by candidate ID; every MPN resolves through an API before it enters the IR. An unresolved MPN is a hard error. Not For New Designs, Last Time Buy and Obsolete block unless the user waives them. Every grounded generator above does this [P].
2. **Part card per MPN** with per-field provenance (extends [part-layout-card](../llm/part-layout-card.md)): pin table and pin roles (PCBSchemaGen ontology, extended); absolute maximums; package; required externals with value rules; layout predicates. Cache verified facts across runs (skidl-skills without a cache: [drift](#what-llm-generated-schematics-most-often-get-wrong)). A human spot-checks every new card (role F1 0.91 → 0.99).
3. **Three-way pin check.** Datasheet pin table, symbol pins and footprint pads agree in count, numbering and package dimensions. For generic symbols bind pin order per MPN from the datasheet (name suffix, or KiCad 11 pin-to-pad map); never default it from the package alone.
4. **Stable identity.** Deterministic UUIDs and refdes ([UUIDs row](schematic-generation-landscape.md#kicad-910-schematic-pitfalls-q5)) let a regenerated schematic keep placement and intent links.

## Reported failure rates

| Measure | Number | Source |
|---|---|---|
| Datasheet KG audit (482 pins), F1 before → after human spot-check | Pin table 0.98 → 1.00; pin role 0.91 → 0.99; constraint inference 0.88 P / 0.85 R / 0.86 F1 → 0.98 | PCBSchemaGen App. A.8 [P] |
| Residual KG errors | Pin aliasing; QFN strap-pin ambiguity; vendor names outside the ontology | same [P] |
| pcbGPT, 400 runs: 28.8% failed; categories among failures (overlapping) | Supporting part missing or wrong type 59.1%; interface connections 40.0%; supporting values 33.9%; local topology 27.0%; component configuration 22.6% | [2606.01188](https://arxiv.org/abs/2606.01188) [P] |
| Errors per design, SchGen code vs raw KiCad text | Symbol 0.06 vs 1.22; connection 0.61 vs 9.42 | [2605.30345](https://arxiv.org/abs/2605.30345) [P] |
| HWE-Bench (qualitative) | Omitted or hallucinated connections on multiplexed and redundant pins; pin-mux conflicts; context overload on ICs with hundreds of pins | [2603.18102](https://arxiv.org/abs/2603.18102) [P] |
| Package hallucination (software analogue; no EE rate for invented MPNs exists) | ≥5.2% commercial, ≥21.7% open models | [2406.10279](https://arxiv.org/abs/2406.10279), USENIX Security 2025 [P] |
| skidl-skills, 9 runs | FT232H internal-regulator pins mishandled in 3 runs (one caught before export); FPGA usable I/O overstated (71 vs 48) twice; BNC and USB-C footprints wrong or unverified in nearly every run; same ADC's minimum clock rate stated differently across runs | [README](https://github.com/devbisme/ai-circuit-design-tests/tree/master/skidl-skills-tests) [P] |
| Field reports | Invented package; SOIC-8 wide part on SOP-8 pads; 6 missing GNDs found only by read-back | [field-failure-modes](../ux/field-failure-modes.md) [P] |

Most failures are invisible to ERC (pcbGPT categories above) [P].

## Schematic verification beyond ERC (Q3)

| Check | What it catches | Prior art |
|---|---|---|
| KiCad ERC | Pin-type conflicts, undriven power inputs, unconnected pins, label problems | Passes 98.3% (easy) and 84.9% (medium/hard) of PCBSchemaGen candidates; full verifier passes 88.1% and 72.4% [P] |
| Pin-role predicates | Supply and ground on one net; required pins floating; diff-pair halves merged; undriven gates | PCBSchemaGen L1b and predicate templates [P] |
| Topology templates | Wrong local topology (half-bridge, synchronous buck, pi filter, RC/LC, divider) | PCBSchemaGen VF2 signatures; Diode `TestBench` path matchers; kicad-happy detectors [P]; [block-recognition](../llm/block-recognition.md) |
| Interfaces | I²C pull-ups and their rail; SPI chip-select mapping; UART TX/RX pairing; USB series resistors, D+ pull-up, ESD, VBUS decoupling | kicad-happy ([methodology](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_schematic.md)); atopile `requires_pulls`; atopile's unique-I²C-address check is commented out in source [P] |
| Voltage domains | Logic crossing rails without a translator; I/O rail vs core rail | kicad-happy cross-domain analysis; atopile power interfaces alias voltage across a bus [P] |
| Derating and stress | Capacitor voltage vs rail. Absolute maximum: ADC clock over its limit; TVS 2.2 V into breakdown at rated input. **MLCC DC bias**: nominal 22 µF measured 11.4 µF at 4.7 V, failed a hold-up spec | kicad-happy §11.3; skidl-skills reviewer; [EEBench](https://eebench.org/blog/can-ai-design-circuit-boards-yet/) [P]; Siemens derating [V] |
| Budgets | Rail current vs regulator rating; sleep current; inrush; sequencing (PG → EN chains) | atopile sums `max_current` across a bus; kicad-happy Tier 3 [P] |
| Protection patterns | TVS/ESD/polyfuse/MOV present on external connectors | kicad-happy, by keywords. No open tool checks a protector's rating against the expected threat [P]/[I] |
| Isolation | Isolator, optocoupler or transformer must join two different domains | kicad-happy §9.16 [P]; spacing is a PCB-stage check ([isolation-creepage](../rules/isolation-creepage.md)) |
| SPICE per block | Divider ratios, filter cutoff and Q, op-amp gain, crystal load, hold-up time | kicad-happy `spice` skill (auto testbenches; ngspice/LTspice/Xyce); HWE-Bench LTspice; EEBench worst-case corners [P] |
| Independent reviewer LLM (fresh context) | HIGH defects ERC missed in 5 of 9 runs: anti-alias filter one order short; ADC clock over absolute max; TVS into breakdown; JTAG at 3.3 V on a 1.8 V bank; mirrored BNC footprint | skidl-skills [P]. DRCY trial: 26 issues over 11 reviews, 4 missed by humans; false positives on DNP/variants ([AllSpice](https://www.allspice.io/post/how-hardware-engineering-teams-evaluate-drcy)) [V] |

- kicad-happy (MIT) detectors match refdes prefixes, `lib_id` and value keywords: use it as an independent second-opinion analyser of emitted `.kicad_sch`, not an oracle [P]/[I]. Thresholds are unsourced heuristics ([critic-stack](../verification/critic-stack.md)). Key our checkers on part-card roles instead of keywords (unconventional names may be missed) [I].
- Commercial checkers build models from the MPN rather than trusting the symbol [V].
- SPICE tooling: ngspice is Modified BSD (KLU LGPLv2, OSDI MPL-2.0), fine as a subprocess ([COPYING](https://sourceforge.net/p/ngspice/ngspice/ci/master/tree/COPYING)) [P]. PySpice 1.5 (2021, GPLv3) is stale; fork InSpice 1.7.0.7 (2026-09) is GPL-3.0-or-later; spicelib 1.6.4 is GPL-3.0 [P]. `kicad-cli sch export netlist --format spice` exports SPICE from the schematic [P].

Rules [I]:
1. **Typed IR.** Typed interfaces (power, I²C, SPI, USB, diff pair) carry parameters; connecting them unifies voltage, sums current, requires pull-ups and unique addresses (atopile semantics). Every pin is **accounted for**: connected, explicit NC, or strapped, each with a reason from the card ("every pin wired" is the wrong invariant).
2. **Check stack, in order:** (1) IR invariants and pin-role predicates; (2) block topology templates; (3) interface rules; (4) domain and derating (net stress vs absolute max, MLCC DC bias, worst-case tolerance); (5) budgets; (6) ngspice testbenches per block; (7) KiCad ERC and [parity](schematic-generation-landscape.md#writer-and-parity-gate-design) on emitted files; (8) fresh-context reviewer LLM that must cite datasheet pages. Every finding is localized to pins ([+24 points](schematic-generation-landscape.md#papers-and-benchmarks-20242026)) in the shared findings schema ([critic-stack](../verification/critic-stack.md)).
3. **Safety domains.** Each net gets a voltage class and isolation domain, LLM-proposed and human-confirmed (mains products, e.g. the 120 V outlet board). A cross-domain part must be isolation-rated with working voltage covering the difference; the PCB engine enforces spacing later.
4. **Protection per external connector:** threat class (ESD, surge, reverse polarity, load dump for automotive) → required protector and ratings. No open tool checks this.

## What LLM-generated schematics most often get wrong

Ordered by how often sources report each class [I]:
1. **Supporting circuitry missing or wrong** (decoupling, pull-ups, feedback, bootstrap). pcbGPT: 59% of failures. JITX's test: "missing many of the necessary connections" ([llm-field-reports](../workflow/llm-field-reports.md)) [P].
2. **Interface wiring:** swapped SPI/I²C/UART nets; JTAG TDI/TDO on wrong pins (DRCY) [P]/[V].
3. **Values:** regulator feedback dividers not matching the datasheet VFB (pcbGPT; DRCY) [P]/[V].
4. **Multi-role pins:** multiplexed, strap, redundant, NC, and internal-regulator pins of interface ICs (HWE-Bench; FT232H in skidl-skills) [P].
5. **Footprint/package mismatch:** connectors, wide vs narrow SOIC, invented packages [P].
6. **Analog spec gaps passing ERC:** filter order, aliasing, clock jitter, DC-bias capacitance, absolute maximums [P].
7. **Facts drift between runs and artifacts:** BOM vs code mismatches (12 stale BOM cells in one run); inconsistent part limits. skidl-skills switched its part-fact cache off to keep runs independent, so no verified fact carried over [P].
8. **Safety-critical choices:** bootstrap diode orientation and synchronous-rectifier variants were where experts disagreed with the PCBSchemaGen verifier [P].

## Placement intent at schematic time (Q4)

| Carrier | How set | What layout does with it | Our IR |
|---|---|---|---|
| KiCad hierarchical sheet per block | One sheet instance per block or channel | 10.0: "Generate Placement Rule Areas" from sheets, component classes or named groups; "Repeat Layout" copies a reference channel after a topology check ([pcbnew 10.0](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html)) [P] | `group`, `region(group, …)` |
| KiCad Component Class (9.0+) | `Component Class` field on a symbol (several allowed), or directive label on a schematic rule area | `hasComponentClass()` in DRC; source of placement rule areas [P] | Role tags (`decap_of:U1`, `hotloop:BUCK1`); `${Class:X}` selectors |
| KiCad net classes (9.0+) | Directive labels, schematic rule areas; several classes per net | Widths, clearances, 10.0 tuning profiles [P] | `tags` / netclass |
| KiCad design blocks | 9.0: schematic fragments; 10.0: schematic + layout fragments | "Apply Design Block Layout" to grouped footprints [P] | Reference-layout copy |
| Symbol UUID path | Automatic | Update PCB links footprints by UUID [P] | Stable keys for the intent file |
| Altium | Per-sheet component classes and **rooms** (Class Generation); `ClassName` parameter; Parameter Set + Blanket directives for net classes; with Constraint Manager enabled only its own classes transfer ([docs](https://altium.com/documentation/altium-designer/classes-schematic-pcb)) [P] | Room per sheet | `region` per block |
| Allegro / OrCAD X | Constraint Manager in Capture; ECSets; constraints inherited from schematic blocks [S] (unverified) | Front-to-back sync | Rule sets per tag |
| atopile | Each module may carry its own `.kicad_pcb`; addresses map sub-layout parts onto the parent; "Pull Group" plugin syncs footprints, tracks, zones [P] | Layout reuse | Reference-layout copy |
| tscircuit | `<constraint>` with `xdist`/`ydist` (edge-to-edge or centre-to-centre), same-x/same-y; `pcbX`/`pcbY`; layout modes [P] | Solver | `near`/`align`, but in mm |
| boardforge | `[[placement.region]]`: sheet or value regex → mm rectangle; anchors; `pin_swap` groups; compaction loop [P] | Own placer | `region`, but in coordinates |
| Quilter | Infers bypass and switcher constraints from schematic patterns ([layout-reuse](../workflow/layout-reuse.md)) [V] | Editable constraint list | Intent detection |

Rules [I]:
1. **Emit KiCad-native carriers** (they survive in KiCad without our tools): one hierarchical sheet per block (placement rule areas, repeated channels); Component Class fields for roles; net classes with current and voltage; design blocks where a reference layout exists.
2. **Emit a `pcb-intent` relation bundle** alongside, keyed by symbol UUID path and refdes: `group`/`region` per block; `near(C, U.pin, tight)` from the card's required externals; `cluster_tight` for hot loops; `board_edge` for connectors from the product brief; keepouts from isolation domains; swappable pin groups for the placer. No millimetres from the LLM ([interfaces-relations-vs-coordinates](../llm/interfaces-relations-vs-coordinates.md), [constraint-ir](../architecture/constraint-ir.md)).

## Open questions

- No study measures invented MPNs or wrong pinouts from free-form LLM part choice. Measure our own: resolve every MPN the LLM types *before* grounding.
- pcbGPT's failure categories overlap; PCBSchemaGen's full failure-trace appendix was not read.
- Commercial schematic checkers (Siemens, Cadstrom, Circuit Mind, DRCY) publish no precision or recall.
- Nexar tiers and DigiKey limits may make catalog-first selection slow on large BOMs; caching policy and licence terms for stored offers are unchecked.
- Allegro room and constraint inheritance details come from secondary snippets.

## Sources

- research notes: none; new research 2026-10-23. Earlier coverage: [part-layout-card](../llm/part-layout-card.md), [datasheet-extraction](../llm/datasheet-extraction.md). Primary sources are linked inline; paper and generator links: [schematic-generation-landscape](schematic-generation-landscape.md#sources).
- also read: [Diode pcb testing](https://github.com/diodeinc/pcb/blob/main/docs/pages/testing.mdx), [InSpice](https://pypi.org/project/InSpice/), [KiCad 9.0 release notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/), [Altium Constraint Manager](https://www.altium.com/documentation/altium-designer/sch-pcb/constraint-manager), [Cadence Capture constraint manager](https://resources.pcb.cadence.com/orcad-x-technical-docs-source/constraint-manager-with-orcad-x-capture), [atopile](https://github.com/atopile/atopile), [PCBSchemaGen_v2](https://github.com/HZou9/PCBSchemaGen_v2), [boardforge](https://github.com/devbisme/boardforge), [tscircuit core](https://github.com/tscircuit/core), [kicad-symbols](https://gitlab.com/kicad/libraries/kicad-symbols).
- see also: [net-role-classification](../llm/net-role-classification.md), [function-to-recipe-mapping](../llm/function-to-recipe-mapping.md), [checkers-power](../rules/checkers-power.md), [decoupling-pdn](../rules/decoupling-pdn.md), [built-in-automation-features](../kicad/built-in-automation-features.md), [delegation-and-expert-review](../workflow/delegation-and-expert-review.md).
