# Per-part "layout card": sources and schema

**TL;DR**
- Distributor and part APIs give **identity, package, datasheet URL and loosely typed parametrics only**. **None carries layout constraints** [P].
- The closest "part plus application circuit" models are **CELUS CUBOs** (typed ports, app-note schematic) and the **PCBSchemaGen pin-role KG**. JEDEC **JEP30 PartModel** is the exchange format, and Flux can generate it from datasheets with AI [V].
- Our layout card should be a superset: identity plus pin→role map plus IBIS facts plus required externals plus typed layout predicates with evidence plus thermal and creepage data, with **provenance per field** [I].
- Expect API churn: the community jlcsearch API stopped returning manufacturer, datasheet and attribute data in 2026-09 [P].

## Key facts

| Source | What it gives | Notes |
|---|---|---|
| Nexar / Octopart GraphQL | `supSearchMpn(q, filters: {case_package: [...]})` → `specs { attribute { name id shortname } displayValue }` | "Not every component will have every attribute"; each part counts against the org limit (default 10) ([Nexar](https://support.nexar.com/support/solutions/articles/101000494582-nexar-playground-graphql-query-examples)) [P] |
| DigiKey Product Information v4 | `POST /products/v4/search/keyword` (HasDatasheet, Has3DModel, HasCadModel) → `DatasheetUrl`, `Parameters[] {ParameterText, ValueText}`; productdetails, substitutions, recommendedproducts; HTTP 429 limits | Read via a secondary doc ([kicad-happy SKILL](https://github.com/aklofas/kicad-happy/blob/main/skills/digikey/SKILL.md)) [P] |
| LCSC / JLCPCB | Product detail: `productModel`, `brandNameEn`, `pdfUrl`, `encapStandard` | jlcsearch dropped `extra` in general search, 2026-09 ([SKILL](https://github.com/aklofas/kicad-happy/blob/main/skills/lcsc/SKILL.md)) [P] |
| JEDEC JEP30 PartModel | Part-data exchange XML | Flux imports and exports it and "can also generate JEP30 files from a datasheet using AI" ([Flux](https://docs.flux.ai/reference/jep30-partmodel-reference.md)) [V] |
| CELUS CUBO | Description; specs; BOM with lifecycle; app-note schematic with decaps and pull-ups; **ports with signal types, electrical constraints, connection requirements**; app-note links. 4-level function hierarchy (L1 "Power Supply" → L2–L4 "Step-Down Converter") | Data from Accuris; an MCP server for Claude [S] ([CUBO](https://www.celus.io/knowledge/what-is-a-cubo)) [V] |
| SnapMagic (SnapEDA) | IPC-7351B footprints; IEEE-315 symbols; nominal 3D models | No public API field reference [S] |
| Flux Knowledge Base | Persistent preferences, including "layout guidelines"; each entry has a **trigger** and a **scope** (user/project) and is suggested from chat | ([Flux](https://docs.flux.ai/reference/knowledge-base.md)) [V] |
| kicad-happy `DatasheetFacts` | Typed per-MPN cache with evidence, confidence trust gates and staleness; covers regulators, diodes, transistors, op-amps, MCUs, crystals | ([doc](https://github.com/aklofas/kicad-happy/blob/main/datasheet-extraction.md)) [P] |
| PCBSchemaGen KG | Per-IC pin roles plus constraint predicates (`kg.json`, `kg_component.json`), MIT | ([repo](https://github.com/HZou9/PCBSchemaGen_v2)) [P] |
| IBIS files | Pin roles, diff pairing, buffer type, edge rates | see [net-role-classification.md](net-role-classification.md) [P] |

## Recommendations for our system

1. **Layout card schema** [I]:
   - identity: MPN, footprint, PDF hash;
   - pin → role map (32-role ontology, extended);
   - IBIS-derived pin facts;
   - required externals with roles;
   - typed layout predicates with evidence and strength;
   - thermal (θJA) and creepage data;
   - per-field provenance;
   - `extraction_audit` (tool-trace hash, evidence pages, consensus count).

   Exportable to JEP30 where useful.
2. **Use distributor APIs** for identity resolution and coarse parametrics (package, current rating, f_sw) only. Isolate them behind adapters to absorb schema churn.
3. **Team overrides** as Flux-style knowledge entries with trigger and scope, merged into recipes.
4. **Licensing:** card *data* we publish is CDLA-Permissive-2.0, so store facts with citations, not copied datasheet text. See [../licensing/reuse-matrix.md](../licensing/reuse-matrix.md).

## Conflicts and open questions

- The official DigiKey v4 field docs, SnapMagic API fields and JEP30 schema contents were not obtained.
- No public structured source of θJA or layout data across vendors was found.

## Sources
- research notes: [netlist_datasheet_understanding.md § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/netlist_datasheet_understanding.md)

See also: [datasheet-extraction.md](datasheet-extraction.md), [net-role-classification.md](net-role-classification.md), [design-understanding-pipeline.md](design-understanding-pipeline.md)
