# Per-part layout card: sources and schema

Scope: where per-part data comes from and the schema of our per-part layout card. Not here: extraction method -> [datasheet-extraction](datasheet-extraction.md); IBIS keywords -> [net-role-classification](net-role-classification.md#ibis-72-keywords).
Keys: layout card, part data, Nexar, Octopart, DigiKey v4, LCSC, JLCPCB, jlcsearch, JEP30 PartModel, CELUS CUBO, SnapMagic, SnapEDA, Flux Knowledge Base, DatasheetFacts, PCBSchemaGen KG, pin role, extraction_audit, provenance

## Part-data sources

No distributor or part API carries layout constraints; they give identity, package, datasheet URL and loosely typed parametrics only [P].

| Source | What it gives | Notes |
|---|---|---|
| Nexar / Octopart GraphQL | `supSearchMpn(q, filters: {case_package: [...]})` -> `specs { attribute { name id shortname } displayValue }` | "Not every component will have every attribute"; each part counts against the org limit (default 10) ([Nexar](https://support.nexar.com/support/solutions/articles/101000494582-nexar-playground-graphql-query-examples)) [P] |
| DigiKey Product Information v4 | `POST /products/v4/search/keyword` (HasDatasheet, Has3DModel, HasCadModel) -> `DatasheetUrl`, `Parameters[] {ParameterText, ValueText}`; productdetails, substitutions, recommendedproducts; HTTP 429 limits | Read via a secondary doc ([kicad-happy SKILL](https://github.com/aklofas/kicad-happy/blob/main/skills/digikey/SKILL.md)) [P] |
| LCSC / JLCPCB | Product detail: `productModel`, `brandNameEn`, `pdfUrl`, `encapStandard` | Community jlcsearch dropped `extra` (manufacturer, datasheet, attributes) in general search, 2026-09 ([SKILL](https://github.com/aklofas/kicad-happy/blob/main/skills/lcsc/SKILL.md)) [P] |
| JEDEC JEP30 PartModel | Part-data exchange XML | Flux imports/exports it and "can also generate JEP30 files from a datasheet using AI" ([Flux](https://docs.flux.ai/reference/jep30-partmodel-reference.md)) [V] |
| CELUS CUBO | Description; specs; BOM with lifecycle; app-note schematic with decaps and pull-ups; **ports with signal types, electrical constraints, connection requirements**; app-note links; 4-level function hierarchy (L1 "Power Supply" -> L2–L4 "Step-Down Converter") | Data from Accuris; MCP server for Claude [S] ([CUBO](https://www.celus.io/knowledge/what-is-a-cubo)) [V] |
| SnapMagic (SnapEDA) | IPC-7351B footprints; IEEE-315 symbols; nominal 3D models | No public API field reference [S] |
| Flux Knowledge Base | Persistent preferences incl. "layout guidelines"; each entry has a **trigger** and a **scope** (user/project), suggested from chat | ([Flux](https://docs.flux.ai/reference/knowledge-base.md)) [V] |
| kicad-happy `DatasheetFacts` | Typed per-MPN cache with evidence, confidence trust gates, staleness; regulators, diodes, transistors, op-amps, MCUs, crystals | ([doc](https://github.com/aklofas/kicad-happy/blob/main/datasheet-extraction.md)) [P] |
| PCBSchemaGen KG | Per-IC pin roles + constraint predicates (`kg.json`, `kg_component.json`), MIT | ([repo](https://github.com/HZou9/PCBSchemaGen_v2)) [P] |
| IBIS files | Pin roles, diff pairing, buffer type, edge rates | -> [net-role-classification](net-role-classification.md#ibis-72-keywords) [P] |

Closest "part + application circuit" models: CELUS CUBOs and the PCBSchemaGen pin-role KG; JEP30 is the exchange format.

## Layout card schema

Superset of the sources, with **provenance per field** [I]:
- identity: MPN, footprint, PDF hash;
- pin -> role map (32-role ontology, extended -> [net-role-classification](net-role-classification.md#pin-semantics));
- IBIS-derived pin facts;
- required externals with roles;
- typed layout predicates with evidence and strength;
- thermal (θJA) and creepage data;
- `extraction_audit` (tool-trace hash, evidence pages, consensus count).

Exportable to JEP30 where useful.

Rules [I]:
1. Use distributor APIs for identity resolution and coarse parametrics (package, current rating, f_sw) only, behind adapters that absorb schema churn.
2. Team overrides are Flux-style knowledge entries with trigger and scope, merged into recipes.
3. Card data we publish is CDLA-Permissive-2.0: store facts with citations, not copied datasheet text -> [licensing/reuse-matrix](../licensing/reuse-matrix.md).

## Open questions

- Official DigiKey v4 field docs, SnapMagic API fields and JEP30 schema contents not obtained.
- No public structured source of θJA or layout data across vendors found.

## Sources
- [netlist_datasheet_understanding.md § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/netlist_datasheet_understanding.md)
