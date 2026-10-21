# Design-understanding pipeline: netlist → blocks → constraints → KiCad intent

**TL;DR**
- Build the front end as:
  1. **deterministic extraction**;
  2. **template/rule recognition**;
  3. **LLM work through tools**: adjudication, detector-writing, staged datasheet extraction;
  4. **user validation**;
  5. **compilation to KiCad-native intent**: net classes, component classes, placement rule areas, `.kicad_dru`;
  6. **constraint-specific post-layout checks**.

  [I]
- The split follows the evidence. LLMs are strong on names, documents and code; they are weak on raw connectivity (2–97%), stage-level grouping (F1 0.31), geometry and long edit chains (80% → 26%) [P].
- **KiCad 9/10 already provide round-tripping carriers** for every annotation: implicit net classes, `Component Class` fields, generated placement rule areas, design blocks [P].
- **Commercial precedent** (Quilter, Flux): detect automatically → user validates → everything else is stated as "generic" [V].
- **A deterministic verifier makes LLM output checkable:** PCBSchemaGen's 5-layer verifier lets Gemma-4-31B pass 81.3% of tasks [P].

## Key facts

### KiCad-native intent carriers [P] ([KiCad 9 Schematic manual](https://docs.kicad.org/9.0/en/eeschema/eeschema.html); [PCB manual](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html))

| Carrier | Behaviour |
|---|---|
| Directive labels | Behave like labels but cannot name a net; the attached net gets the directive's Net Class |
| **Implicit net classes** | A typed class not in the list "can't be assigned any design settings… but can still be used in DRC rule queries" |
| Multiple Net Class fields | All listed classes are assigned; a directive on a bus applies to all members |
| Rule areas | Anything crossing or inside gets the class of the attached directive |
| **Component classes** | A `Component Class` symbol field, or a directive with that field on a rule area; multiple allowed; applies to footprints; used for multichannel and custom DRC |
| DRC functions (KiCad 9) | `A.hasNetclass('x')`, `A.hasComponentClass('X')` (**footprints only**, per users), `A.memberOfFootprint('${Class:X}')`, `A.ComponentClass == 'A,B'` ([release notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/)) |
| **Generate Placement Rule Areas** | Per hierarchical sheet or component class; "minimum size rectangle that encloses their constituent footprints"; optional grouping |
| Repeat Layout | Copies a reference channel's placement and routing when topologies match |
| KiCad 10 | PCB design blocks; Tuning Profiles; graphical DRC rule editor; variants; unconstrained pin/gate swap ([release](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)) |

### Precedents for detect → validate → check
- **Quilter Circuit Comprehension:** reads the schematic and board, auto-detects physics constraints, and has the user validate them. Undetected signals are "generic, low-speed digital". "Use native object classes whenever possible". No symmetric multichannel layout ([docs](https://docs.quilter.ai/using-quilter/define-physics-comprehensions)) [V].
- **Flux:** Net Type is inferred and editable; Copilot changes the schematic "with your approval"; the Knowledge Base suggests persistent rules from chat ([Flux](https://docs.flux.ai/reference/knowledge-base.md)) [V].
- **kicad-happy `design_intent`:** product class, IPC class, market, `confidence`, `detection_signals`, per-field `source`; **asks the user when confidence < 0.5** ([design-intent.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/references/design-intent.md)) [P].
- **copperhead:** "Nothing starts without a spec"; edit tools stay unavailable until a validated change proposal exists ([README](https://github.com/copperheadhq/copperhead)) [V].
- **atopile:** layouts persist across regeneration by hierarchical address (`usb_c.esd_protection.package`) and sub-PCB templates [P, secondary].
- **PCBSchemaGen:** a 5-layer verifier (ERC, role, template, VF2 topology, power invariants); with it, Gemma-4-31B passes 81.3% ([2602.00510](https://arxiv.org/abs/2602.00510)) [P].
- **Validation ≠ simulation:** 10.7% of circuits were rejected by the topology validator yet ran silently in ngspice ([2609.26830](https://arxiv.org/abs/2609.26830)) [P].

### Evaluation datasets

| Dataset | Content | Licence / access |
|---|---|---|
| BenchPCNP | 50 boards, 54 module labels | CC BY 4.0 |
| open-schematics | 87.9k schematic/PCB records, no labels | CC-BY-4.0 tag; source licences vary |
| Ohmatic human-verified-v1 | 1,000 KiCad/Eagle schematics | CC-BY-4.0 |
| PCBSchemaGen benchmarks | 227 tasks, 480 real ICs | MIT. The HF card (67/63/35) and README (40/48/77) difficulty splits differ |
| PCB-QA | 480 QA over 8 KiCad projects | — |
| PCB-Bench | 174 OSHWHub boards with descriptions | — |
| HWE-Bench | 300 tasks, 2,914 datasheets | — |
| OmniLayout/OmniRouting | 1,681 designs | **Conflict:** CC-BY-4.0 per the paper vs no licence and 5 public boards per third-party recon |

## Recommendations for our system

### Pipeline
D = deterministic, L = LLM, U = user [I].

1. **Ingest (D):** parse `.kicad_sch`/`.kicad_pro`; build the part–net–pin graph; expand hierarchy. Capture existing intent (net classes and patterns, directive labels, `Component Class` fields, sheet names, power symbols). Export compact hierarchical JSON plus query tools.
2. **Part resolution (D, L for gaps):** MPN → distributor API → hashed datasheet PDF plus IBIS if available. When the MPN is missing, the LLM proposes candidates marked `proposed`. See [part-layout-card.md](part-layout-card.md).
3. **Layout card (staged L, D validation):** chunked extraction with evidence; a tool-call audit; validators for units, pin existence against the symbol, and datasheet vs symbol pin names. See [datasheet-extraction.md](datasheet-extraction.md).
4. **Net roles (D layered, L leftovers):** see [net-role-classification.md](net-role-classification.md).
5. **Blocks (D templates, L detector-writing):** see [block-recognition.md](block-recognition.md). Never ask the LLM for stage-level groupings.
6. **Recipes → constraints plus checks (D, L fills parameters):** see [function-to-recipe-mapping.md](function-to-recipe-mapping.md).
7. **Validate (U):** a Quilter-style review screen. Each detected constraint shows its evidence and editable fields; accept/reject is recorded; undetected nets are explicitly "generic low-speed". Ask questions only for high-impact, low-confidence fields, such as interface speed, max current on unnamed rails, or split vs single ground.
8. **Compile (D):**
   - real classes for width, clearance and gap; **implicit classes for semantic tags** (e.g. `ROLE_SW_NODE`);
   - `Component Class` per block (`BLK_BUCK1`) plus per-role classes (`ROLE_CIN_HF`);
   - **generated placement rule areas per block** as placer region seeds;
   - `.kicad_dru` using `memberOfFootprint('${Class:…}')`; tuning profiles;
   - soft objectives in a placer JSON.
9. **Verify (D):** DRC, constraint-specific checks, and structural LVS as a separate stage. Violations feed back to the placer and router.

### Schema additions
- `constraints[].checks`, e.g. `{"type": "pin_distance", "a": "C12.1", "b": "U3.VIN", "max_mm": 10, "source": "Quilter example range"}`.
- `nets.*.ibis` = `{model_type, diff_pin, ramp_20_80_ps}`.
- `parts.*.layout_card.extraction_audit` = `{trace hash, evidence pages, consensus count}`.

See [../architecture/constraint-intent-ir.md](../architecture/constraint-intent-ir.md).

### Division of labour
- **LLM:**
  - normalizing pin names to roles;
  - interpreting naming and sheet names;
  - staged datasheet extraction with evidence;
  - turning qualitative guidelines into typed predicates;
  - writing detector code;
  - generating targeted questions and explanations.
- **Deterministic:**
  - parsing, connectivity and every graph query;
  - VF2;
  - numeric derivation (widths, impedance, Vout, loop area);
  - IBIS parsing and unit normalization;
  - KiCad file writing;
  - all checks;
  - staleness and audit logs;
  - all geometry (no LLM millimetres without a cited source).
- **Team overrides:** Flux-style knowledge entries with a trigger and scope ("our bucks always get a 0402 HF cap on the same layer").

## Conflicts and open questions

- No public dataset combines block labels, net roles **and** layout constraints on KiCad boards. A candidate path is mining net classes, component classes and DRU rules from open-schematics and the kicad-happy corpus. How many designers use these features is unmeasured.
- Quilter's and Flux's detection accuracy is undisclosed.
- The exact KiCad 10 `.kicad_dru` syntax for component-class conditions was not re-verified.

## Sources
- research notes:
  - [netlist_datasheet_understanding.md § 5, § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/netlist_datasheet_understanding.md)
  - [llm_for_eda.md § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)

See also: [block-recognition.md](block-recognition.md), [net-role-classification.md](net-role-classification.md), [function-to-recipe-mapping.md](function-to-recipe-mapping.md), [datasheet-extraction.md](datasheet-extraction.md), [../ux/explanations-and-alternatives.md](../ux/explanations-and-alternatives.md)
