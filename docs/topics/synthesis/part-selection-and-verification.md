# Part selection, schematic verification and placement intent

**TL;DR**
- **Part identity must be a lookup, never generated text.** The LLM chooses among catalog results, and every MPN is resolved through an API before it enters the IR.
  - Every grounded generator does this: pcbGPT, atopile, CircuitLM, PCBSchemaGen [P].
  - No published rate exists for invented MPNs. The nearest analogue is software packages: at least 5.2% invented by commercial models and 21.7% by open models [P].
- **A pinout is trusted only when three sources agree:** the datasheet pin table, the symbol's pins and the footprint's pads (and package).
  - Staged extraction is accurate for pin tables (F1 0.98) but weaker for pin roles (0.91) and constraints (0.86) before a human spot-check [P].
  - One pipeline's connector footprints were wrong or unverified "in nearly every run" [P].
- **Most failures in generated schematics are invisible to ERC.** Of failed pcbGPT runs:
  - 59% had missing or wrong supporting parts;
  - 40% had interface wiring errors;
  - 34% had wrong values [P].

  Checks must be typed and datasheet-driven: required externals per pin role, bus rules, voltage domains, derating including MLCC DC bias, budgets, SPICE for blocks, and an independent reviewer [I].
- **Reusable open prior art:** kicad-happy's detectors (MIT), PCBSchemaGen's verifier (MIT) and atopile's interface semantics. Commercial checkers build models from the MPN rather than trusting the symbol [P]/[V].
- **Hand placement intent through KiCad-native carriers plus a relation bundle.** The carriers are one hierarchical sheet per block, Component Class fields for roles, and net classes. The bundle is keyed by stable symbol UUID paths. KiCad 10 turns sheets, classes and groups into placement rule areas and repeated layouts [P].

## Key facts

Tags: [P] primary; [S] snippet/secondary; [V] vendor; [I] inference.

### Part data sources (Q2)

| Source | What it gives | Limits and terms |
|---|---|---|
| KiCad libraries | Symbols, footprints and 3D models. Generic symbols encode pin order in their names (`D_Dual_CommonAnode_AKK`, `Q_NJFET_GSD`). In master, generic `Q_NMOS` has pins `D/G/S` bound to pads by new pin-to-pad maps [P] | CC-BY-SA 4.0, with article 3 waived for designs that use them ([licence](https://www.kicad.org/libraries/license/)). No MPN, stock or lifecycle data [P] |
| DigiKey Product Information v4 | Keyword and parametric search; `ProductStatus` (Active, Active Not Stocked, Discontinued, Last Time Buy, Not For New Designs, Obsolete); substitutions; datasheet URL | 120 requests/min and 1,000/day by default ([docs](https://developer.digikey.com/documentation)) [P]. Status values as parsed by kicad-happy [P] |
| Mouser Search API | MPN and keyword search; lifecycle values (New Product, End of Life, …) | 30 calls/min on the free tier [S] |
| Nexar / Octopart | Aggregated offers, specs, lifecycle, datasheets | Evaluation: 100 matched parts, with lifecycle, specs and datasheets. Standard: 2,000 parts, without them. Pro: 15,000, with them as add-ons ([plans](https://nexar.com/compare-plans)) [P] |
| element14 | Specs and datasheets | 2 calls/s and 1,000/day "courtesy" allowance [S] |
| JLCPCB / LCSC | Stock, basic/extended status, price, package | The official API needs approval [S]. The community jlcparts SQLite dump is about 11 GB [S]. jlcsearch dropped manufacturer and datasheet fields in 2026-09 ([part-layout-card](../llm/part-layout-card.md)) [P] |
| pcbparts MCP | Parametric search over 630k+ in-stock JLCPCB parts; live Mouser/DigiKey stock; footprints via SamacSys; pinouts from EasyEDA symbols; about 285 OSHW reference boards | MIT code, but a hosted service; third-party data terms not checked ([repo](https://github.com/Averyy/pcbparts-mcp)) [P]/[V] |
| EasyEDA/LCSC symbols | A symbol and footprint per LCSC part | The common importer, easyeda2kicad, is AGPL-3.0 [P]; contributed data of unknown accuracy [I] |

Per-part layout data is in [../llm/part-layout-card.md](../llm/part-layout-card.md); extraction methods in [../llm/datasheet-extraction.md](../llm/datasheet-extraction.md).

### How tools keep parts real and pinouts right

| Tool | Mechanism | Gap |
|---|---|---|
| pcbGPT | Searches only the installed KiCad libraries (embedding plus lexical). An invalid pin returns the valid pin list. Footprints are validated at creation. If datasheet extraction fails, the part is reported "unavailable" so the agent picks another [P] | No stock or lifecycle check |
| atopile | Parametric pick from a parts database within the solver's bounds. The picked part's attributes are attached back as constraints [P] | R, C and L only; other parts take EasyEDA pinouts |
| PCBSchemaGen | Per-IC knowledge graph induced from the datasheet: pin table → pin roles → predicates [P] | The task supplies the ICs; 47-IC library |
| CircuitLM | Curated component KB with canonical pinouts [P] | KB scale unknown |
| skidl-skills | A sourcing agent (pcbparts); a datasheet librarian; `kipart` symbols built from datasheet pin tables, with pin counts checked [P] | Footprint check only confirms the file exists. When datasheet downloads failed (FTDI 403s), pins were written from memory |
| AllSpice DRCY | Agentic datasheet retrieval; a critic weights pin-function coverage at 40%; k-run consensus ([datasheet-extraction](../llm/datasheet-extraction.md)) [P] | No published accuracy |
| Siemens Xpedition schematic analysis (ex-Valydate) | Builds models from the BOM MPN, not from the symbol ([blog](https://blogs.sw.siemens.com/electronic-systems-design/2017/11/04/a-brief-introduction-to-schematic-integrity-analysis/)) [V] | Proprietary; rule list unpublished |

### Reported failure rates

| Measure | Number | Source |
|---|---|---|
| Datasheet KG audit (482 pins), F1 before → after spot-check | Pin table 0.98 → 1.00; pin role 0.91 → 0.99; constraint inference 0.88 P / 0.85 R / 0.86 F1 → 0.98 | PCBSchemaGen App. A.8 [P] |
| Residual KG errors | Pin aliasing; QFN strap-pin ambiguity; vendor names outside the ontology | same [P] |
| pcbGPT, 400 runs: 28.8% failed. Categories among failures (overlapping) | Supporting part missing or wrong type 59.1%; interface connections 40.0%; supporting values 33.9%; local topology 27.0%; component configuration 22.6% | [2606.01188](https://arxiv.org/abs/2606.01188) [P] |
| Errors per design, SchGen code vs raw KiCad text | Symbol errors 0.06 vs 1.22; connection errors 0.61 vs 9.42 | [2605.30345](https://arxiv.org/abs/2605.30345) [P] |
| HWE-Bench (qualitative) | Omissions or hallucinated connections on multiplexed and redundant pins; pin-mux conflicts; context overload on ICs with hundreds of pins | [2603.18102](https://arxiv.org/abs/2603.18102) [P] |
| Package hallucination (software analogue) | ≥5.2% commercial, ≥21.7% open models | [2406.10279](https://arxiv.org/abs/2406.10279), USENIX Security 2025 [P] |
| skidl-skills, 9 runs | FT232H internal-regulator pins mishandled in 3 runs (one caught before export); FPGA usable I/O overstated (71 vs 48) twice; BNC and USB-C footprints wrong or unverified in nearly every run; the same ADC's minimum clock rate stated differently across runs | [README](https://github.com/devbisme/ai-circuit-design-tests/tree/master/skidl-skills-tests) [P] |
| Field reports | Invented package; SOIC-8 wide part on SOP-8 pads; 6 missing GNDs found only by read-back | [../ux/field-failure-modes.md](../ux/field-failure-modes.md) [P] |

### Schematic verification beyond ERC (Q3)

| Check | What it catches | Prior art |
|---|---|---|
| KiCad ERC | Pin-type conflicts, undriven power inputs, unconnected pins, label problems | Passes 98.3% (easy) and 84.9% (medium/hard) of PCBSchemaGen candidates; the full verifier passes 88.1% and 72.4% [P] |
| Pin-role predicates | Supply and ground on the same net; required pins floating; diff-pair halves merged; undriven gates | PCBSchemaGen L1b and its predicate templates [P] |
| Topology templates | Wrong local topology (half-bridge, synchronous buck, pi filter, RC/LC, divider) | PCBSchemaGen VF2 signatures; Diode `TestBench` path matchers; kicad-happy detectors [P]; see [../llm/block-recognition.md](../llm/block-recognition.md) |
| Interfaces | I²C pull-ups and the rail they go to; SPI chip-select mapping; UART TX/RX pairing; USB series resistors, D+ pull-up, ESD and VBUS decoupling | kicad-happy ([methodology](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_schematic.md)); atopile `requires_pulls`. atopile's unique-I²C-address check is commented out in source [P] |
| Voltage domains | Logic crossing rails without a translator; I/O rail vs core rail | kicad-happy cross-domain analysis; atopile power interfaces alias voltage across a bus [P] |
| Derating and stress | Capacitor voltage vs rail. Absolute maximum: an ADC clock over its limit; a TVS 2.2 V into breakdown at the rated input. **MLCC DC bias**: a nominal 22 µF part measured 11.4 µF at 4.7 V and failed a hold-up spec | kicad-happy §11.3; skidl-skills reviewer; [EEBench](https://eebench.org/blog/can-ai-design-circuit-boards-yet/) [P]; Siemens derating [V] |
| Budgets | Rail current vs regulator rating; sleep current; inrush; power sequencing (PG → EN chains) | atopile sums `max_current` across a bus; kicad-happy Tier 3 analyses [P] |
| Protection patterns | Presence of TVS/ESD/polyfuse/MOV on external connectors | kicad-happy detects them by keywords. No open tool checks a protector's rating against the expected threat [P]/[I] |
| Isolation | An isolator, optocoupler or transformer must join two different domains | kicad-happy §9.16 [P]. Spacing is a PCB-stage check ([../rules/isolation-creepage.md](../rules/isolation-creepage.md)) |
| SPICE per block | Divider ratios, filter cutoff and Q, op-amp gain, crystal load, hold-up time | kicad-happy `spice` skill (auto testbenches; ngspice/LTspice/Xyce); HWE-Bench LTspice; EEBench worst-case corners [P] |
| Independent reviewer LLM (fresh context) | HIGH defects ERC missed in 5 of 9 runs: anti-alias filter one order short; ADC clock over its absolute maximum; TVS into breakdown; JTAG at 3.3 V on a 1.8 V bank; mirrored BNC footprint | skidl-skills [P]. DRCY trial: 26 issues over 11 reviews, 4 of them missed by humans; false positives on DNP/variants ([AllSpice](https://www.allspice.io/post/how-hardware-engineering-teams-evaluate-drcy)) [V] |

kicad-happy's detectors match on refdes prefixes, `lib_id` and value keywords, so they are second opinions, not oracles [P]. Its thresholds are unsourced heuristics ([../verification/critic-stack.md](../verification/critic-stack.md)).

**SPICE tooling.**
- ngspice is Modified BSD (KLU is LGPLv2, OSDI is MPL-2.0), so it runs fine as a subprocess ([COPYING](https://sourceforge.net/p/ngspice/ngspice/ci/master/tree/COPYING)) [P].
- PySpice 1.5 (2021, GPLv3) is stale. Its fork InSpice 1.7.0.7 (2026-09) is GPL-3.0-or-later; spicelib 1.6.4 is GPL-3.0 [P].
- `kicad-cli sch export netlist --format spice` exports a SPICE netlist from the schematic [P].

### What LLM-generated schematics most often get wrong

Ordered by how often the sources report each class [I]:
1. **Supporting circuitry missing or wrong**, e.g. decoupling, pull-ups, feedback and bootstrap parts. pcbGPT: 59% of failures. JITX's test: "missing many of the necessary connections" ([../workflow/llm-field-reports.md](../workflow/llm-field-reports.md)) [P].
2. **Interface wiring.** Swapped SPI/I²C/UART nets; JTAG TDI/TDO on the wrong pins (DRCY) [P]/[V].
3. **Values.** Regulator feedback dividers that don't match the datasheet's VFB (pcbGPT; DRCY) [P]/[V].
4. **Pins with more than one role.** Multiplexed, strap, redundant and NC pins, and internal-regulator pins of interface ICs (HWE-Bench; FT232H in skidl-skills) [P].
5. **Footprint/package mismatch.** Connectors, wide vs narrow SOIC, invented packages [P].
6. **Analog spec gaps** that pass ERC: filter order, aliasing, clock jitter, DC-bias capacitance, absolute maximums [P].
7. **Facts drift between runs and between artifacts.** BOM vs code mismatches (12 stale BOM cells in one run); inconsistent part limits. The part-fact cache was switched off to keep runs independent, so no verified fact carried over [P].
8. **Safety-critical choices.** Bootstrap diode orientation and synchronous-rectifier variants were where experts disagreed with the verifier (PCBSchemaGen) [P].

### Placement intent at schematic time (Q4)

| Carrier | How it is set | What layout does with it | Maps to our IR |
|---|---|---|---|
| KiCad hierarchical sheet per block | One sheet instance per block or channel | 10.0: "Generate Placement Rule Areas" from sheets, component classes or named groups; "Repeat Layout" copies a reference channel after a topology check ([pcbnew 10.0](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html)) [P] | `group`, `region(group, …)` |
| KiCad Component Class (9.0+) | A `Component Class` field on a symbol (several allowed), or a directive label on a schematic rule area | `hasComponentClass()` in DRC; source of placement rule areas [P] | Role tags (`decap_of:U1`, `hotloop:BUCK1`); `${Class:X}` selectors |
| KiCad net classes (9.0+) | Directive labels, schematic rule areas; several classes per net | Widths, clearances, 10.0 tuning profiles [P] | `tags` / netclass |
| KiCad design blocks | 9.0: schematic fragments. 10.0: schematic plus layout fragments | "Apply Design Block Layout" to the grouped footprints [P] | Reference-layout copy |
| Symbol UUID path | Automatic | Update PCB links footprints by UUID [P] | Stable keys for the intent file |
| Altium | Per-sheet component classes and **rooms** (Class Generation); `ClassName` parameter; Parameter Set + Blanket directives for net classes. With Constraint Manager enabled, only its own classes transfer ([docs](https://altium.com/documentation/altium-designer/classes-schematic-pcb)) [P] | Room per sheet | `region` per block |
| Allegro / OrCAD X | Constraint Manager in Capture; ECSets; constraints inherited from schematic blocks [S] | Front-to-back sync | Rule sets per tag |
| atopile | Each module may carry its own `.kicad_pcb`; addresses map sub-layout parts onto the parent; a "Pull Group" plugin syncs footprints, tracks and zones [P] | Layout reuse | Reference-layout copy |
| tscircuit | `<constraint>` with `xdist`/`ydist` (edge-to-edge or centre-to-centre) and same-x/same-y; `pcbX`/`pcbY`; layout modes [P] | Solver | `near`/`align`, but in mm |
| boardforge | `[[placement.region]]`: sheet or value regex → mm rectangle; anchors; `pin_swap` groups; compaction loop [P] | Own placer | `region`, but in coordinates |
| Quilter | Infers bypass and switcher constraints from schematic patterns ([../workflow/layout-reuse.md](../workflow/layout-reuse.md)) [V] | Editable constraint list | Intent detection |

## Recommendations for our system

**Parts (Q2)** [I]:
1. **Catalog-first selection.**
   - Retrieve candidates by parametric query: KiCad libraries for symbols and footprints, plus JLCPCB/LCSC and DigiKey/Mouser for stock, lifecycle and price.
   - The LLM picks by candidate ID. An MPN that doesn't resolve is a hard error, never a warning.
   - Treat Not For New Designs, Last Time Buy and Obsolete as blocking unless the user waives them.
2. **A part card per MPN** with per-field provenance (extend [../llm/part-layout-card.md](../llm/part-layout-card.md)). It holds:
   - the pin table and pin roles (PCBSchemaGen's ontology, extended);
   - absolute maximums and package;
   - required externals with value rules;
   - layout predicates.

   Cache verified facts across runs; skidl-skills shows what happens without a cache. A human spot-checks every new card, which takes role F1 from 0.91 to 0.99.
3. **Three-way pin check.** The datasheet pin table, the symbol pins and the footprint pads must agree in count, numbering and package dimensions. For generic symbols, bind the pin order per MPN from the datasheet (check the name suffix, or the pin-to-pad map in KiCad 11); never default it from the package alone.
4. **Adapters behind one interface** for DigiKey (OAuth, 1,000/day), Mouser, Nexar (100-part evaluation tier) and LCSC, with caching for rate limits and schema churn. Use LCSC/EasyEDA data, but not the AGPL importer code.

**Verification (Q3)** [I]:
1. **Typed IR, so checks are cheap.**
   - Typed interfaces (power, I²C, SPI, USB, diff pair) carry parameters.
   - Connecting them unifies voltage, sums current, and requires pull-ups and unique addresses (the atopile semantics).
   - Every pin is **accounted for**: connected, explicitly NC, or strapped, each with a reason from the card. "Every pin wired" is the wrong invariant.
2. **Check stack, in order:**
   1. IR invariants and pin-role predicates;
   2. block topology templates;
   3. interface rules;
   4. domain and derating (net stress vs absolute maximum, with DC bias for MLCCs, at worst-case tolerance);
   5. budgets;
   6. ngspice testbenches per block;
   7. KiCad ERC and parity on the emitted files;
   8. a fresh-context reviewer LLM that must cite datasheet pages.

   Every finding is localized to pins (PCBSchemaGen: +24 points over pass/fail) and uses the shared findings schema ([../verification/critic-stack.md](../verification/critic-stack.md)).
3. **Safety domains.** Each net gets a voltage class and isolation domain, proposed by the LLM and confirmed by a human (mains products such as the 120 V outlet board). Anything that crosses domains must be an isolation-rated part whose working voltage covers the difference. Spacing is enforced later by the PCB engine.
4. **Protection rules per external connector:** the threat class (ESD, surge, reverse polarity, load dump for automotive) maps to a required protector and its ratings. No open tool checks this today.

**Placement intent (Q4)** [I]:
1. **Emit KiCad-native carriers:**
   - one hierarchical sheet per block, for placement rule areas and repeated channels;
   - Component Class fields for roles;
   - net classes with current and voltage;
   - design blocks where a reference layout exists.

   These survive in KiCad without our tools.
2. **Emit a `pcb-intent` relation bundle alongside them**, keyed by symbol UUID path and refdes. It holds:
   - `group`/`region` per block;
   - `near(C, U.pin, tight)` from the part card's required externals;
   - `cluster_tight` for hot loops;
   - `board_edge` for connectors from the product brief;
   - keepouts from isolation domains;
   - swappable pin groups for the placer.

   No millimetres from the LLM ([../llm/interfaces-relations-vs-coordinates.md](../llm/interfaces-relations-vs-coordinates.md), [../architecture/constraint-ir.md](../architecture/constraint-ir.md)).
3. **Stable identity.** Deterministic UUIDs and refdes let a regenerated schematic keep its placement and intent links.

## Conflicts and open questions

- **No measured EE hallucination rate.** No study measures invented MPNs or wrong pinouts from free-form LLM part choice. We should measure our own: resolve every MPN the LLM types *before* grounding.
- **Unread detail.** pcbGPT's failure categories overlap. PCBSchemaGen's full failure-trace appendix was not read.
- **Vendor-only numbers.** Commercial schematic checkers (Siemens, Cadstrom, Circuit Mind, DRCY) publish no precision or recall.
- **Shallow heuristics.** kicad-happy's keyword detectors may miss parts named unconventionally. Our checkers should key on part-card roles instead.
- **Untested limits.** Nexar's tiers and DigiKey's limits may make catalog-first selection slow on large BOMs; caching policy and licence terms for stored offers are unchecked.
- **Unverified Allegro detail.** Allegro's room and constraint inheritance details come from secondary snippets.

## Sources

- research notes: none; this is new research (2026-10-23). Earlier coverage: [../llm/part-layout-card.md](../llm/part-layout-card.md), [../llm/datasheet-extraction.md](../llm/datasheet-extraction.md).
- papers: [PCBSchemaGen](https://arxiv.org/html/2602.00510v2), [pcbGPT](https://arxiv.org/html/2606.01188), [SchGen](https://arxiv.org/html/2605.30345v1), [HWE-Bench](https://arxiv.org/html/2603.18102), [package hallucinations](https://arxiv.org/abs/2406.10279).
- code: [kicad-happy](https://github.com/aklofas/kicad-happy), [atopile](https://github.com/atopile/atopile), [PCBSchemaGen_v2](https://github.com/HZou9/PCBSchemaGen_v2), [pcbparts-mcp](https://github.com/Averyy/pcbparts-mcp), [ai-circuit-design-tests](https://github.com/devbisme/ai-circuit-design-tests), [boardforge](https://github.com/devbisme/boardforge), [tscircuit core](https://github.com/tscircuit/core), [Diode pcb testing](https://github.com/diodeinc/pcb/blob/main/docs/pages/testing.mdx), [InSpice](https://pypi.org/project/InSpice/).
- data and APIs: [KiCad library licence](https://www.kicad.org/libraries/license/), [kicad-symbols](https://gitlab.com/kicad/libraries/kicad-symbols), [DigiKey API docs](https://developer.digikey.com/documentation), [Nexar plans](https://nexar.com/compare-plans).
- KiCad: [9.0 release notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/), [pcbnew 10.0 manual](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html).
- vendors: [Altium classes](https://altium.com/documentation/altium-designer/classes-schematic-pcb), [Altium Constraint Manager](https://www.altium.com/documentation/altium-designer/sch-pcb/constraint-manager), [Cadence Capture constraint manager](https://resources.pcb.cadence.com/orcad-x-technical-docs-source/constraint-manager-with-orcad-x-capture), [Siemens schematic integrity](https://blogs.sw.siemens.com/electronic-systems-design/2017/11/04/a-brief-introduction-to-schematic-integrity-analysis/), [AllSpice DRCY evaluation](https://www.allspice.io/post/how-hardware-engineering-teams-evaluate-drcy), [EEBench](https://eebench.org/blog/can-ai-design-circuit-boards-yet/).

See also: [schematic-generation-landscape.md](schematic-generation-landscape.md), [../llm/net-role-classification.md](../llm/net-role-classification.md), [../llm/function-to-recipe-mapping.md](../llm/function-to-recipe-mapping.md), [../rules/checkers-power.md](../rules/checkers-power.md), [../rules/decoupling-pdn.md](../rules/decoupling-pdn.md), [../kicad/built-in-automation-features.md](../kicad/built-in-automation-features.md), [../workflow/delegation-and-expert-review.md](../workflow/delegation-and-expert-review.md)
