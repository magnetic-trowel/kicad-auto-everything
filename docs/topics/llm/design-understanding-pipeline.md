# Design-understanding pipeline: netlist -> blocks -> constraints -> KiCad intent

Scope: the front-end pipeline from schematic to KiCad-native intent, who does each step (deterministic / LLM / user), and the KiCad carriers. Not here: per-step detail -> [block-recognition](block-recognition.md), [net-role-classification](net-role-classification.md), [datasheet-extraction](datasheet-extraction.md), [function-to-recipe-mapping](function-to-recipe-mapping.md); IR schema -> [architecture/constraint-ir](../architecture/constraint-ir.md); DRC rule syntax -> [kicad/drc-rule-language-reference](../kicad/drc-rule-language-reference.md).
Keys: design understanding, front end, intent compilation, directive label, implicit net class, component class, placement rule area, Generate Placement Rule Areas, Repeat Layout, design blocks, detect-validate-check, Quilter Circuit Comprehension, design_intent, copperhead spec gate, PCBSchemaGen verifier, structural LVS, BenchPCNP, open-schematics, Ohmatic, division of labour

## Why the split

LLMs are strong on names, documents and code; weak on raw connectivity (2–97%), stage-level grouping (F1 0.31), geometry and long edit chains (80% -> 26%) -> [block-recognition](block-recognition.md#llm-netlist-reading-benchmarks) [P]. A deterministic verifier makes LLM output checkable (PCBSchemaGen 5-layer verifier -> [synthesis/schematic-generation-landscape](../synthesis/schematic-generation-landscape.md#papers-and-benchmarks-20242026)) [P]. Commercial precedent (Quilter, Flux): detect automatically -> user validates -> everything else stated as "generic" [V].

## Pipeline

D = deterministic, L = LLM, U = user [I].

1. **Ingest (D):** parse `.kicad_sch`/`.kicad_pro`; part–net–pin graph; expand hierarchy. Capture existing intent (net classes and patterns, directive labels, `Component Class` fields, sheet names, power symbols). Export compact hierarchical JSON + query tools.
2. **Part resolution (D, L for gaps):** MPN -> distributor API -> hashed datasheet PDF + IBIS if available; missing MPN -> LLM proposes candidates marked `proposed` -> [part-layout-card](part-layout-card.md).
3. **Layout card (staged L, D validation):** chunked extraction with evidence; tool-call audit; validators for units, pin existence against the symbol, datasheet vs symbol pin names -> [datasheet-extraction](datasheet-extraction.md).
4. **Net roles (D layered, L leftovers)** -> [net-role-classification](net-role-classification.md).
5. **Blocks (D templates, L detector-writing)** -> [block-recognition](block-recognition.md). Never ask the LLM for stage-level groupings.
6. **Recipes -> constraints + checks (D, L fills parameters)** -> [function-to-recipe-mapping](function-to-recipe-mapping.md).
7. **Validate (U):** Quilter-style review screen; each detected constraint shows evidence and editable fields; accept/reject recorded; undetected nets explicitly "generic low-speed". Ask only for high-impact, low-confidence fields (interface speed, max current on unnamed rails, split vs single ground).
8. **Compile (D):** real classes for width, clearance, gap; **implicit classes for semantic tags** (`ROLE_SW_NODE`); `Component Class` per block (`BLK_BUCK1`) + per-role classes (`ROLE_CIN_HF`); generated placement rule areas per block as placer region seeds; `.kicad_dru` using `memberOfFootprint('${Class:…}')`; tuning profiles; soft objectives in a placer JSON.
9. **Verify (D):** DRC, constraint-specific checks, structural LVS as a separate stage (validation ≠ simulation, see below); violations feed back to placer and router.

Schema additions -> [architecture/constraint-ir](../architecture/constraint-ir.md):
- `constraints[].checks`, e.g. `{"type": "pin_distance", "a": "C12.1", "b": "U3.VIN", "max_mm": 10, "source": "Quilter example range"}`;
- `nets.*.ibis` = `{model_type, diff_pin, ramp_20_80_ps}`;
- `parts.*.layout_card.extraction_audit` = `{trace hash, evidence pages, consensus count}`.

## Division of labour

| LLM | Deterministic |
|---|---|
| normalize pin names to roles; interpret naming and sheet names; staged datasheet extraction with evidence; qualitative guidelines -> typed predicates; write detector code; targeted questions and explanations | parsing, connectivity, every graph query; VF2; numeric derivation (widths, impedance, Vout, loop area); IBIS parsing, unit normalization; KiCad file writing; all checks; staleness and audit logs; all geometry (no LLM millimetres without a cited source) |

Team overrides: Flux-style knowledge entries with trigger and scope ("our bucks always get a 0402 HF cap on the same layer").

## KiCad-native intent carriers

KiCad 9/10 carry every annotation round-trip [P] ([KiCad 9 Schematic manual](https://docs.kicad.org/9.0/en/eeschema/eeschema.html); [PCB manual](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html)).

| Carrier | Behaviour |
|---|---|
| Directive labels | Like labels but cannot name a net; the attached net gets the directive's Net Class |
| **Implicit net classes** | A typed class not in the list "can't be assigned any design settings… but can still be used in DRC rule queries" |
| Multiple Net Class fields | All listed classes assigned; a directive on a bus applies to all members |
| Rule areas | Anything crossing or inside gets the class of the attached directive |
| **Component classes** | `Component Class` symbol field, or a directive with that field on a rule area; multiple allowed; applies to footprints; used for multichannel and custom DRC |
| DRC functions (KiCad 9) | `A.hasNetclass('x')`, `A.hasComponentClass('X')` (**footprints only**, per users), `A.memberOfFootprint('${Class:X}')`, `A.ComponentClass == 'A,B'` ([release notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/)) |
| **Generate Placement Rule Areas** | Per hierarchical sheet or component class; "minimum size rectangle that encloses their constituent footprints"; optional grouping |
| Repeat Layout | Copies a reference channel's placement and routing when topologies match |
| KiCad 10 | PCB design blocks; Tuning Profiles; graphical DRC rule editor; variants; unconstrained pin/gate swap ([release](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)) |

## Precedents for detect -> validate -> check

- Quilter Circuit Comprehension: reads schematic and board, auto-detects physics constraints, user validates; undetected signals "generic, low-speed digital"; "Use native object classes whenever possible"; no symmetric multichannel layout ([docs](https://docs.quilter.ai/using-quilter/define-physics-comprehensions)) [V].
- Flux: Net Type inferred and editable; Copilot changes the schematic "with your approval"; Knowledge Base suggests persistent rules from chat ([Flux](https://docs.flux.ai/reference/knowledge-base.md)) [V].
- kicad-happy `design_intent`: product class, IPC class, market, `confidence`, `detection_signals`, per-field `source`; **asks the user when confidence < 0.5** ([design-intent.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/references/design-intent.md)) [P].
- copperhead: "Nothing starts without a spec"; edit tools unavailable until a validated change proposal exists ([README](https://github.com/copperheadhq/copperhead)) [V].
- atopile: layouts persist across regeneration by hierarchical address (`usb_c.esd_protection.package`) and sub-PCB templates [P, secondary].
- PCBSchemaGen: 5-layer verifier (ERC, role, template, VF2 topology, power invariants) -> [synthesis/schematic-generation-landscape](../synthesis/schematic-generation-landscape.md#papers-and-benchmarks-20242026) ([2602.00510](https://arxiv.org/abs/2602.00510)) [P].
- Validation ≠ simulation: 10.7% of circuits rejected by the topology validator ran silently in ngspice -> [block-recognition](block-recognition.md#llm-netlist-reading-benchmarks) ([2609.26830](https://arxiv.org/abs/2609.26830)) [P].

## Evaluation datasets

| Dataset | Content | Licence / access |
|---|---|---|
| BenchPCNP | 50 boards, 54 module labels | CC BY 4.0 |
| open-schematics | 87.9k schematic/PCB records, no labels | CC-BY-4.0 tag; source licences vary |
| Ohmatic human-verified-v1 | 1,000 KiCad/Eagle schematics | CC-BY-4.0 |
| PCBSchemaGen benchmarks | 227 tasks, 480 real ICs | MIT; HF card (67/63/35) and README (40/48/77) difficulty splits differ |
| PCB-QA | 480 QA over 8 KiCad projects | — |
| PCB-Bench | 174 OSHWHub boards with descriptions | — |
| HWE-Bench | 300 tasks, 2,914 datasheets | — |
| OmniLayout/OmniRouting | 1,681 designs | **Conflict:** CC-BY-4.0 per paper vs no licence and 5 public boards per third-party recon |

## Open questions

- No public dataset combines block labels, net roles **and** layout constraints on KiCad boards; candidate path: mine net classes, component classes and DRU rules from open-schematics and the kicad-happy corpus. Designer uptake of these features unmeasured.
- Quilter's and Flux's detection accuracy undisclosed.
- Exact KiCad 10 `.kicad_dru` syntax for component-class conditions not re-verified.

## Sources
- [netlist_datasheet_understanding.md § 5, § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/netlist_datasheet_understanding.md)
- [llm_for_eda.md § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
